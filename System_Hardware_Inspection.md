# System Hardware Inspection Report

> **Generated:** October 8, 2026  
> **Host Machine:** Lenovo LOQ 15ARP9 (`83JC`)  
> **Environment:** Windows 11 Home Single Language (64-bit, Build 26300)

---

## 1. System Overview & Motherboard

| Component | Specification |
| :--- | :--- |
| **Device Model** | **Lenovo LOQ 15ARP9** |
| **Model Type / SKU** | `83JC` (`LENOVO_MT_83JC_BU_idea_FM_LOQ 15ARP9`) |
| **Motherboard** | Lenovo `LNVNB161216` |
| **BIOS Version** | `PQCN30WW` |
| **BIOS Release Date** | May 11, 2026 |
| **Chassis / Form Factor** | Gaming Notebook |
| **System Architecture** | x64-based PC |

---

## 2. Processor (CPU)

| Attribute | Value |
| :--- | :--- |
| **Processor Name** | **AMD Ryzen 7 7435HS** |
| **Microarchitecture** | Zen 3+ (Rembrandt-R, 6nm TSMC) |
| **Physical Cores** | **8 Cores** |
| **Logical Processors (Threads)** | **16 Threads** |
| **Base Clock** | 3.10 GHz |
| **Max Boost Clock** | Up to 4.50 GHz |
| **L2 Cache** | 4,096 KB (512 KB per core) |
| **L3 Cache** | 16,384 KB (16 MB shared) |
| **Hardware Virtualization** | AMD-V / SVM Enabled (`Hyper-V Active: True`) |
| **Integrated Graphics (iGPU)** | **None** (Ryzen 7 7435HS is a dedicated-dGPU SKU; display output routes directly through NVIDIA dGPU) |

---

## 3. Dedicated Graphics Processing Unit (GPU)

| Attribute | Specification |
| :--- | :--- |
| **GPU Model** | **NVIDIA GeForce RTX 4060 Laptop GPU** |
| **Architecture** | Ada Lovelace (AD107) |
| **Video Memory (VRAM)** | **8 GB GDDR6** (8,188 MiB addressable) |
| **Driver Version** | `617.14` (DirectX Driver: `32.0.16.1714`) |
| **Idle / Base State** | P8 Power State, ~3.5 W draw, ~46°C idle temp |
| **Status** | Healthy (`OK`) |

---

## 4. System Memory (RAM)

| Attribute | Value |
| :--- | :--- |
| **Installed Capacity** | **24.0 GB** (23.69 GB visible to OS) |
| **Memory Generation** | **DDR5** SODIMM |
| **Configured Transfer Rate** | **4800 MT/s** (4800 MHz) |
| **Memory Channels** | Dual-Channel (128-bit bus width) |

### Memory Slot Details
| Slot Locator | Channel / Bank | Capacity | Manufacturer | Part Number | Speed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DIMM 0` | P0 CHANNEL A | 12.0 GB | Ramaxel Technology | `RMSB3400KB06IVF-4800` | 4800 MHz |
| `DIMM 0` | P0 CHANNEL B | 12.0 GB | Ramaxel Technology | `RMSB3400KB06IVF-4800` | 4800 MHz |

---

## 5. Storage Subsystem

### Physical Drive
| Attribute | Details |
| :--- | :--- |
| **Drive Model** | **Micron MTFDKCD512QFM-1BD1AABLA** (Micron 2400 Series) |
| **Bus Interface** | NVMe PCIe 4.0 x4 |
| **Media Type** | High-density Solid-State Drive (SSD) |
| **Capacity** | 512 GB (476.94 GiB raw) |
| **Health & Operational Status** | **Healthy / OK** |

### Logical Partition
| Drive Letter | File System | Total Volume Size | Free Space | Utilization |
| :--- | :--- | :--- | :--- | :--- |
| `C:` (System) | NTFS | 475.89 GB | **252.43 GB** | ~47% used / ~53% free |

---

## 6. Internal Display Panel

| Attribute | Specification |
| :--- | :--- |
| **Display Manufacturer** | AU Optronics (AUO) |
| **Native Resolution** | **1920 × 1080** (Full HD, 16:9 Aspect Ratio) |
| **Refresh Rate** | **144 Hz** |
| **Color Quality** | 32-bit True Color |
| **Panel Technology** | High Refresh Rate IPS Gaming Display |

---

## 7. Battery & Power Diagnostics

| Parameter | Diagnostic Reading |
| :--- | :--- |
| **Battery Device Name** | `L23M4PK4` |
| **Factory Design Capacity** | 60,000 mWh (60.0 Wh) |
| **Current Full Charge Capacity**| 54,600 mWh (54.6 Wh) |
| **Battery Health Percentage** | **91.0%** (~9.0% wear degradation) |
| **Lifetime Cycle Count** | **508 charge cycles** |
| **Status** | Healthy (`OK`) |

---

## 8. Network Interfaces

| Interface Name | Adapter Model | Connection Status | Link Speed | Physical MAC Address |
| :--- | :--- | :--- | :--- | :--- |
| **Wi-Fi** | MediaTek Wi-Fi 6 MT7921 802.11ax Adapter | **Connected (Up)** | **1.2 Gbps** | `44-FA-66-F2-33-F3` |
| **Ethernet** | Realtek PCIe Gigabit Ethernet Controller | Disconnected | 1 Gbps capable | `40-C2-BA-59-DF-EA` |

---

## 9. Audio & Multimedia

- **Integrated Audio Codec:** Realtek High Definition Audio
- **Audio Processing / Spatial Engine:** Nahimic Virtual Surround & VAD Engine
- **Digital / Display Audio:** NVIDIA High Definition Audio (HDMI/DisplayPort output)

---

## 10. Operating System & Virtualization

- **Operating System:** Microsoft Windows 11 Home Single Language (64-bit)
- **Kernel Build:** `10.0.26300` (Version 2009)
- **Virtualization Support:** Hypervisor Present (`True`), Device Guard Smart Status: Off
- **Time Zone:** UTC+05:30 (India Standard Time)
