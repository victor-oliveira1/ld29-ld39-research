# LD29 / LD39 Research

Research notes and archived files for the LD29 and LD39 phone-to-display
mirroring devices. The repository brings together observations about USB
identification, the Android app, firmware update metadata, and video settings.

## Contents

- [Repository map](#repository-map)
- [App download](#app-download)
- [Linux capture (LD39)](#linux-capture-ld39)
- [Android capture (LD29)](#android-capture-ld29)
- [Research notes and scope](#research-notes-and-scope)

## Repository map

| Path | Contents |
| --- | --- |
| [`app/`](./app/) | Archived Android and iOS app packages; see the [app notes](./app/README.md). |
| [`firmwares/`](./firmwares/) | Firmware packages grouped by product or model. |
| [`screenshots/`](./screenshots/) | Screenshots captured during the research. |
| [`server-assets/`](./server-assets/) | Captured app/device update JSON and notes on observed service requests. |
| [`video-modes/`](./video-modes/) | Video mode settings and encoder log samples. |

## App download

The app's `latest` download endpoint, as recorded during this research, is:

<https://svc2.onebitplay.com/mirror_app/product_files/androids/latest>

This endpoint may redirect to a different APK over time. Previously downloaded
packages, download details, and the observed redirect are documented in
[`app/README.md`](./app/README.md).

## Linux capture (LD39)

The following is a captured Linux USB/audio enumeration for an LD39 cable.
It is a device observation, not a complete hardware specification.

```
== DMESG ==
[   48.190990] usb 1-2: new high-speed USB device number 4 using xhci_hcd
[   55.771002] usb 1-2: new high-speed USB device number 5 using xhci_hcd
[   55.908661] usb 1-2: New USB device found, idVendor=18d1, idProduct=2d04, bcdDevice=99.99
[   55.908717] usb 1-2: New USB device strings: Mfr=1, Product=2, SerialNumber=0
[   55.908744] usb 1-2: Product: Mirroring Suit
[   55.908763] usb 1-2: Manufacturer: Sage Inc.
[   56.203298] usbcore: registered new interface driver snd-usb-audio

== APP ==
App Version: 1.1.15498
Device Version: 1.407.14506
Device Info: vid:1 pid:1281

== lspci -vvv ==
Bus 001 Device 005: ID 18d1:2d04 Google Inc. Android Open Accessory device (accessory + audio)
Negotiated speed: High Speed (480Mbps)
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               0.00
  bDeviceClass            0 [unknown]
  bDeviceSubClass         0 [unknown]
  bDeviceProtocol         0 
  bMaxPacketSize0        64
  idVendor           0x18d1 Google Inc.
  idProduct          0x2d04 Android Open Accessory device (accessory + audio)
  bcdDevice           99.99
  iManufacturer           1 Sage Inc.
  iProduct                2 Mirroring Suit
  iSerial                 0 
  bNumConfigurations      1
OTG Descriptor:
  bLength                 3
  bDescriptorType         9
  bmAttributes         0x03
    SRP (Session Request Protocol)
    HNP (Host Negotiation Protocol)
  Configuration Descriptor:
    bLength                 9
    bDescriptorType         2
    wTotalLength       0x0088
    bNumInterfaces          3
    bConfigurationValue     2
    iConfiguration          3 Android Accessory
    bmAttributes         0xe0
      Self Powered
      Remote Wakeup
    MaxPower              200mA
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        0
      bAlternateSetting       0
      bNumEndpoints           2
      bInterfaceClass       255 Vendor Specific Class
      bInterfaceSubClass    255 Vendor Specific Subclass
      bInterfaceProtocol      0 
      iInterface              4 Android Accessory Interface
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x81  EP 1 IN
        bmAttributes            2
          Transfer Type            Bulk
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0200  1x 512 bytes
        bInterval               0
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x01  EP 1 OUT
        bmAttributes            2
          Transfer Type            Bulk
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0200  1x 512 bytes
        bInterval               0
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        1
      bAlternateSetting       0
      bNumEndpoints           0
      bInterfaceClass         1 Audio
      bInterfaceSubClass      1 Control Device
      bInterfaceProtocol      0 
      iInterface              0 
      AudioControl Interface Descriptor:
        bLength                10
        bDescriptorType        36
        bDescriptorSubtype      1 (HEADER)
        bcdADC               1.00
        wTotalLength       0x000a
        bInCollection           2
        baInterfaceNr(0)        0
        baInterfaceNr(1)        1
      AudioControl Interface Descriptor:
        bLength                12
        bDescriptorType        36
        bDescriptorSubtype      2 (INPUT_TERMINAL)
        bTerminalID             1
        wTerminalType      0x0101 USB Streaming
        bAssocTerminal          0
        bNrChannels             2
        wChannelConfig     0x0003
          Left Front (L)
          Right Front (R)
        iChannelNames           0 
        iTerminal               0 
      AudioControl Interface Descriptor:
        bLength                 9
        bDescriptorType        36
        bDescriptorSubtype      3 (OUTPUT_TERMINAL)
        bTerminalID             3
        wTerminalType      0x0301 Speaker
        bAssocTerminal          2
        bSourceID               2
        iTerminal               0 
      AudioControl Interface Descriptor:
        bLength                 9
        bDescriptorType        36
        bDescriptorSubtype      6 (FEATURE_UNIT)
        bUnitID                 2
        bSourceID               1
        bControlSize            2
        bmaControls(0)     0x0003
          Mute Control
          Volume Control
        iFeature                0 
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        2
      bAlternateSetting       0
      bNumEndpoints           0
      bInterfaceClass         1 Audio
      bInterfaceSubClass      2 Streaming
      bInterfaceProtocol      0 
      iInterface              0 
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        2
      bAlternateSetting       1
      bNumEndpoints           1
      bInterfaceClass         1 Audio
      bInterfaceSubClass      2 Streaming
      bInterfaceProtocol      0 
      iInterface              0 
      AudioStreaming Interface Descriptor:
        bLength                 7
        bDescriptorType        36
        bDescriptorSubtype      1 (AS_GENERAL)
        bTerminalLink           1
        bDelay                  1 frames
        wFormatTag         0x0001 PCM
      AudioStreaming Interface Descriptor:
        bLength                11
        bDescriptorType        36
        bDescriptorSubtype      2 (FORMAT_TYPE)
        bFormatType             1 (FORMAT_TYPE_I)
        bNrChannels             2
        bSubframeSize           2
        bBitResolution         16
        bSamFreqType            1 Discrete
        tSamFreq[ 0]        48000
      Endpoint Descriptor:
        bLength                 9
        bDescriptorType         5
        bEndpointAddress     0x03  EP 3 OUT
        bmAttributes            1
          Transfer Type            Isochronous
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x00c8  1x 200 bytes
        bInterval               1
        bRefresh                0
        bSynchAddress           0
        AudioStreaming Endpoint Descriptor:
          bLength                 7
          bDescriptorType        37
          bDescriptorSubtype      1 (EP_GENERAL)
          bmAttributes         0x01
            Sampling Frequency
          bLockDelayUnits         1 Milliseconds
          wLockDelay         0x0100
can't get debug descriptor: Resource temporarily unavailable
Device Status:     0x0001
  Self Powered
```

## Android capture (LD29)

The following Android USB service output was captured with an LD29 cable.

```
Added device UsbDevice
[
  mName=/dev/bus/usb/001/003,
  mVendorId=6353,
  mProductId=11524,
  mClass=0,
  mSubclass=0,
  mProtocol=0,
  mManufacturerName=Sage Inc.,
  mProductName=Mirroring Suit,
  mVersion=0.0,
  mSerialNumber=null,
  mConfigurations=[
    UsbConfiguration[
      mId=2,
      mName=Android Accessory,
      mAttributes=224,
      mMaxPower=100,
      mInterfaces=[
        UsbInterface[
          mId=0,
          mAlternateSetting=0,
          mName=Android Accessory Interface,
          mClass=255,
          mSubclass=255,
          mProtocol=0,
          mEndpoints=[
            UsbEndpoint[
              mAddress=129,
              mAttributes=2,
              mMaxPacketSize=512,
              mInterval=0
            ],
            UsbEndpoint[
              mAddress=1,
              mAttributes=2,
              mMaxPacketSize=512,
              mInterval=0
            ]
          ]
        ],
        UsbInterface[
          mId=1,
          mAlternateSetting=0,
          mName=null,
          mClass=1,
          mSubclass=1,
          mProtocol=0,
          mEndpoints=[]
        ],
        UsbInterface[
          mId=2,
          mAlternateSetting=0,
          mName=null,
          mClass=1,
          mSubclass=2,
          mProtocol=0,
          mEndpoints=[]
        ],
        UsbInterface[
          mId=2,
          mAlternateSetting=1,
          mName=null,
          mClass=1,
          mSubclass=2,
          mProtocol=0,
          mEndpoints=[
            UsbEndpoint[
              mAddress=3,
              mAttributes=1,
              mMaxPacketSize=200,
              mInterval=1
            ]
          ]
        ]
      ]
    ]
  ]
]
```

## Research notes and scope

- Text files, screenshots, and JSON files are research captures. Service
  responses, URLs, and available versions can change.
- Update metadata and firmware packages are organized under
  [`server-assets/`](./server-assets/) and [`firmwares/`](./firmwares/).
- Confirm the exact model and firmware compatibility before using any
  archived package. These files are not installation instructions.
- This is an independent research archive, not vendor documentation.
