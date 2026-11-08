import Foundation
import ARKit
import Vision
import Network
import Combine
import ImageIO
import simd

final class ARKitGazeSession: NSObject, ObservableObject, ARSessionDelegate {
    @Published private(set) var status = "Ready"
    @Published private(set) var networkStatus = "Disconnected"
    @Published private(set) var faceStatus = "Waiting"
    @Published private(set) var handStatus = "Waiting"
    @Published private(set) var packetCount = 0
    @Published private(set) var lastGaze: SIMD3<Float>?
    @Published private(set) var lastPinchRatio: Double?
    @Published private(set) var errorText = ""

    var isRunning = false

    private let session = ARSession()
    private let frameQueue = DispatchQueue(label: "com.gazetouch.arkit.frames", qos: .userInteractive)
    private let networkQueue = DispatchQueue(label: "com.gazetouch.arkit.network", qos: .userInitiated)
    private var connection: NWConnection?
    private var lastSendTime: TimeInterval = 0
    private var frameCounter = 0
    private var sequenceNumber: UInt64 = 0
    private var cachedPinchRatio: Double?
    private var cachedHandFound = false
    private let handRequest = VNDetectHumanHandPoseRequest()

    override init() {
        super.init()
        handRequest.maximumHandCount = 1
    }

    func showError(_ message: String) {
        DispatchQueue.main.async { self.errorText = message }
    }

    func start(host: String, port: UInt16) {
        guard ARFaceTrackingConfiguration.isSupported else {
            showError("ARKit Face Tracking is not supported on this device.")
            return
        }
        guard let endpointPort = NWEndpoint.Port(rawValue: port) else {
            showError("Invalid UDP port.")
            return
        }

        stop()
        errorText = ""
        let link = NWConnection(host: NWEndpoint.Host(host), port: endpointPort, using: .udp)
        connection = link
        link.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                switch state {
                case .ready:
                    self?.networkStatus = "UDP ready · \(host):\(port)"
                case .failed(let error):
                    self?.networkStatus = "Network error"
                    self?.errorText = error.localizedDescription
                case .waiting(let error):
                    self?.networkStatus = "Waiting: \(error.localizedDescription)"
                case .cancelled:
                    self?.networkStatus = "Disconnected"
                default:
                    break
                }
            }
        }
        link.start(queue: networkQueue)

        session.delegate = self
        session.delegateQueue = frameQueue

        let config = ARFaceTrackingConfiguration()
        config.isLightEstimationEnabled = false
        config.maximumNumberOfTrackedFaces = 1
        session.run(config, options: [.resetTracking, .removeExistingAnchors])

        isRunning = true
        DispatchQueue.main.async {
            self.status = "Starting ARKit…"
            self.faceStatus = "Waiting for face"
            self.handStatus = "Waiting for hand"
            self.networkStatus = "Connecting"
            self.packetCount = 0
        }
    }

    func stop() {
        isRunning = false
        session.pause()
        connection?.cancel()
        connection = nil
        DispatchQueue.main.async {
            self.status = "Stopped"
            self.networkStatus = "Disconnected"
        }
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        guard isRunning else { return }

        frameCounter += 1
        // Run Vision hand detection on the same ARKit camera frames; no second camera app.
        // Run every third frame to leave enough processing time for face tracking.
        if frameCounter % 3 == 0 {
            updateHandPose(from: frame.capturedImage)
        }

        // Send gaze telemetry at up to 30 Hz.
        guard frame.timestamp - lastSendTime >= (1.0 / 30.0) else { return }
        lastSendTime = frame.timestamp

        guard let face = frame.anchors.compactMap({ $0 as? ARFaceAnchor }).first else {
            DispatchQueue.main.async { self.faceStatus = "Face not detected" }
            sequenceNumber &+= 1
            sendPacket([
                "version": 2,
                "sequence": sequenceNumber,
                "timestamp": frame.timestamp,
                "face_detected": false,
                "hand_detected": cachedHandFound,
                "pinch_ratio": cachedPinchRatio as Any? ?? NSNull()
            ])
            return
        }

        let gaze = face.lookAtPoint
        let leftEye4 = face.leftEyeTransform.columns.3
        let rightEye4 = face.rightEyeTransform.columns.3
        let leftEye = SIMD3<Float>(leftEye4.x, leftEye4.y, leftEye4.z)
        let rightEye = SIMD3<Float>(rightEye4.x, rightEye4.y, rightEye4.z)
        let eyeMidpoint = (leftEye + rightEye) * 0.5
        let gazeVector = gaze - eyeMidpoint
        let safeZ = max(0.025, abs(gazeVector.z))
        let gazeFeatures = [
            Double(gazeVector.x / safeZ),
            Double(gazeVector.y / safeZ)
        ]
        guard gazeFeatures.allSatisfy({ $0.isFinite && abs($0) < 5.0 }) else {
            return
        }

        sequenceNumber &+= 1
        let packet: [String: Any] = [
            "version": 2,
            "sequence": sequenceNumber,
            "timestamp": frame.timestamp,
            "face_detected": true,
            "gaze": [Double(gaze.x), Double(gaze.y), Double(gaze.z)],
            "gaze_features": gazeFeatures,
            "eye_midpoint": [Double(eyeMidpoint.x), Double(eyeMidpoint.y), Double(eyeMidpoint.z)],
            "left_eye_transform": matrixArray(face.leftEyeTransform),
            "right_eye_transform": matrixArray(face.rightEyeTransform),
            "face_transform": matrixArray(face.transform),
            "hand_detected": cachedHandFound,
            "pinch_ratio": cachedPinchRatio as Any? ?? NSNull()
        ]

        DispatchQueue.main.async {
            self.faceStatus = "Tracked"
            self.status = "ARKit running"
            self.lastGaze = gaze
            self.lastPinchRatio = self.cachedPinchRatio
        }
        sendPacket(packet)
    }

    private func updateHandPose(from pixelBuffer: CVPixelBuffer) {
        do {
            let handler = VNImageRequestHandler(
                cvPixelBuffer: pixelBuffer,
                orientation: .up,
                options: [:]
            )
            try handler.perform([handRequest])
            guard let observation = handRequest.results?.first else {
                cachedHandFound = false
                cachedPinchRatio = nil
                DispatchQueue.main.async { self.handStatus = "Hand not detected" }
                return
            }

            func point(_ name: VNHumanHandPoseObservation.JointName) -> CGPoint? {
                guard let p = try? observation.recognizedPoint(name), p.confidence >= 0.25 else {
                    return nil
                }
                return p.location
            }

            guard let thumb = point(.thumbTip),
                  let index = point(.indexTip),
                  let indexMCP = point(.indexMCP),
                  let littleMCP = point(.littleMCP) else {
                cachedHandFound = false
                cachedPinchRatio = nil
                return
            }

            let palmWidth = hypot(indexMCP.x - littleMCP.x, indexMCP.y - littleMCP.y)
            guard palmWidth > 0.015 else {
                cachedHandFound = false
                cachedPinchRatio = nil
                return
            }

            let gap = hypot(thumb.x - index.x, thumb.y - index.y)
            cachedPinchRatio = Double(gap / palmWidth)
            cachedHandFound = true
            DispatchQueue.main.async { self.handStatus = "Tracked" }
        } catch {
            cachedHandFound = false
            cachedPinchRatio = nil
            DispatchQueue.main.async { self.handStatus = "Vision error" }
        }
    }

    private func matrixArray(_ m: simd_float4x4) -> [Double] {
        [
            Double(m.columns.0.x), Double(m.columns.0.y), Double(m.columns.0.z), Double(m.columns.0.w),
            Double(m.columns.1.x), Double(m.columns.1.y), Double(m.columns.1.z), Double(m.columns.1.w),
            Double(m.columns.2.x), Double(m.columns.2.y), Double(m.columns.2.z), Double(m.columns.2.w),
            Double(m.columns.3.x), Double(m.columns.3.y), Double(m.columns.3.z), Double(m.columns.3.w)
        ]
    }

    private func sendPacket(_ object: [String: Any]) {
        guard let connection,
              let data = try? JSONSerialization.data(withJSONObject: object, options: [.fragmentsAllowed]) else {
            return
        }
        connection.send(content: data, completion: .contentProcessed { [weak self] error in
            if let error {
                DispatchQueue.main.async { self?.errorText = error.localizedDescription }
            } else {
                DispatchQueue.main.async { self?.packetCount += 1 }
            }
        })
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        DispatchQueue.main.async {
            self.status = "ARKit failed"
            self.errorText = error.localizedDescription
        }
    }

    func sessionWasInterrupted(_ session: ARSession) {
        DispatchQueue.main.async { self.status = "Camera interrupted" }
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        DispatchQueue.main.async { self.status = "Restarting ARKit…" }
        guard isRunning else { return }
        let config = ARFaceTrackingConfiguration()
        config.isLightEstimationEnabled = false
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
    }

    deinit {
        session.pause()
        connection?.cancel()
    }
}
