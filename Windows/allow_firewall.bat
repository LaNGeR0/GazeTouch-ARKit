@echo off
echo This command adds an inbound Windows Firewall rule for GazeTouch UDP 50555.
netsh advfirewall firewall add rule name="GazeTouch ARKit UDP" dir=in action=allow protocol=UDP localport=50555
pause
