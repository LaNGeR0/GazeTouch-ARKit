import SwiftUI
import ARKit

struct ContentView: View {
    @StateObject private var bridge = ARKitGazeSession()
    @State private var pcAddress = "192.168.1.100"
    @State private var portText = "50555"

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "eye.circle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.blue)

            Text("GazeTouch · iPhone sensor")
                .font(.title2.bold())

            Text("Eyes + hand pinch · local Wi-Fi · no Iriun needed")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                Text("Windows PC IPv4 address")
                    .font(.caption.weight(.semibold))
                TextField("192.168.1.100", text: $pcAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.decimalPad)
                    .textFieldStyle(.roundedBorder)

                Text("UDP port")
                    .font(.caption.weight(.semibold))
                TextField("50555", text: $portText)
                    .keyboardType(.numberPad)
                    .textFieldStyle(.roundedBorder)
            }
            .frame(maxWidth: 420)

            Button {
                guard let port = UInt16(portText), !pcAddress.isEmpty else {
                    bridge.showError("Check the PC IP address and UDP port.")
                    return
                }
                bridge.start(host: pcAddress, port: port)
            } label: {
                Label("Connect and start tracking", systemImage: "dot.radiowaves.left.and.right")
                    .frame(maxWidth: 420)
            }
            .buttonStyle(.borderedProminent)
            .disabled(bridge.isRunning)

            Button(role: .destructive) {
                bridge.stop()
            } label: {
                Label("Stop", systemImage: "stop.fill")
            }
            .disabled(!bridge.isRunning)

            GroupBox("Status") {
                VStack(alignment: .leading, spacing: 7) {
                    statusLine("ARKit", value: bridge.status)
                    statusLine("Network", value: bridge.networkStatus)
                    statusLine("Face", value: bridge.faceStatus)
                    statusLine("Hand", value: bridge.handStatus)
                    statusLine("Packets", value: "\(bridge.packetCount)")
                    if let gaze = bridge.lastGaze {
                        statusLine("lookAtPoint", value: String(
                            format: "x %.3f · y %.3f · z %.3f", gaze.x, gaze.y, gaze.z
                        ))
                    }
                    if let pinch = bridge.lastPinchRatio {
                        statusLine("Pinch ratio", value: String(format: "%.3f", pinch))
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: 520)

            Text("Keep the iPhone mounted under the monitor, front camera facing you. Both devices must be on the same local network.")
                .font(.footnote)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .frame(maxWidth: 480)

            if !bridge.errorText.isEmpty {
                Text(bridge.errorText)
                    .foregroundStyle(.red)
                    .font(.footnote)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .systemGroupedBackground))
    }

    @ViewBuilder
    private func statusLine(_ title: String, value: String) -> some View {
        HStack {
            Text(title).foregroundStyle(.secondary)
            Spacer()
            Text(value).fontWeight(.medium).multilineTextAlignment(.trailing)
        }
        .font(.callout)
    }
}
