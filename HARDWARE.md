# Hardware Used

This project uses external hardware components to control the coffee brewing process. These components are connected to the Raspberry Pi 5 and controlled via Python.

## DC Motor (Stirring Mechanism)

- **Model**: Bringsmart small DC gear motor, 12 V, 160 RPM, 8 mm shaft, torque 10 kg·cm.
- **Purpose**: Drives the stirring mechanism that controls the rotation speed of the brewing device.
- **Link**: https://www.amazon.co.jp/dp/B08N52HJNX
- **Control**: The motor is powered by a 12 V supply and its speed is controlled via a motor driver connected to the Raspberry Pi's GPIO pins.

## Solenoid Valve (Water Flow Control)

- **Model**: U.S. Solid solenoid valve, DC 12 V, normally closed, 1/2″ (DN15) stainless steel body with VITON seal.
- **Purpose**: Controls the flow of water for each pour during extraction.
- **Link**: https://www.amazon.co.jp/dp/B00APDA6Z6
- **Control**: The valve is controlled via a MOSFET or relay board driven by the Raspberry Pi's GPIO pins.

## BITalino (EDA and ECG Sensors)

- **Device**: BITalino (r)evolution Board used to capture electrodermal activity (EDA) and electrocardiogram (ECG) signals.
- **Communication**: Communicates with the Raspberry Pi via Bluetooth.
- **Role**: Provides real‑time psychophysiological data that drives the adaptive extraction algorithm.

## Other Equipment

- **Computer**: Raspberry Pi 5 running the Python control code.
- **Brewing apparatus**: Standard pour‑over coffee dripper and filter.
- **Immersive elements**: Headphones and an eye mask to block external audiovisual cues during the brewing experience.
