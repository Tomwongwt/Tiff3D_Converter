[English](README.md) | [中文](README_zh.md)

# Tiff3D Converter

将 3D+Time TIFF 序列（通常来自 ScanImage 显微镜）转换为 OME-TIFF、IMS (Imaris) 或 2D TIFF 系列。

© 2026 Tom Wong - Tsinghua University. Powered by DeepSeek & Claude Code.

## 功能特性

- **GUI 界面**（Tkinter），方便参数配置和预览
- 读取 ScanImage 生成的 BigTIFF 文件（Z-fast, T-slow 帧顺序）
- 自动从 TIFF 头部检测 ScanImage 元数据（Z 切片数、Z 步长）
- 支持三种输出格式：
  - **OME-TIFF** — 4D (T,Z,Y,X) 堆栈，含 OME-XML 元数据，可在 Imaris 中打开
  - **IMS (.ims)** — Imaris 原生格式（需要捆绑的 `ImarisConvertBioformats`）
  - **2D-TIFF Series** — 每层一个文件 `name_T####_Z####.tif`
- 优雅处理不完整的最后一个文件 — 自动截断到最近的 Z 整数倍

## 环境要求

- Python 3.8+
- `tifffile >= 2024.1`
- `numpy >= 1.24`

安装依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

### GUI

```bash
python tiff3d_gui.py
```

1. 选择包含 `.tif`/`.tiff` 文件的**输入文件夹**
2. 配置**参数**：
   - **Z 切片数** — 如果可用，自动从 ScanImage 元数据中检测
   - **每文件时间点数** — 每个 TIFF 文件包含的 volume 数量
   - **Z 步长 (µm)** — Z 方向的体素大小
   - **XY 像素尺寸 (µm)** — 自动或手动
3. 选择**输出文件夹**和**输出名称**
4. 选择**输出格式**（OME-TIFF / IMS / 2D-TIFF Series）
5. 点击 **Convert**

### 库调用

```python
import reader
import converter
import tiff2d_writer

# 构建转换计划
plan = converter.ConversionPlan.from_directory(
    "path/to/tiffs", z_per_volume=21, t_per_file=10
)

# 检查一致性
issues = plan.check_consistency()

# 写入 OME-TIFF
tiff2d_writer.write_ome_tiff(
    "output.ome.tif",
    plan.shape,
    plan.dtype,
    plan.iter_timepoints(),
    xy_pixel_um=0.9,
    z_step_um=2.0,
)
```

## 输出格式

| 格式 | 扩展名 | 说明 |
|---|---|---|
| OME-TIFF | `.ome.tif` | 单个 4D BigTIFF，含 OME 元数据，兼容 Imaris |
| IMS | `.ims` | Imaris 原生格式（需捆绑 `ImarisConvertBioformats`） |
| 2D-TIFF Series | `.tif` (每层) | 每个 (T,Z) 一个文件 — `name_T0000_Z0000.tif` |

## 帧排序

转换器假设 **Z-fast, T-slow** 帧排序（ScanImage 默认）：

```
Frame 0: T0 Z0
Frame 1: T0 Z1
...
Frame Z-1: T0 Z(Z-1)
Frame Z: T1 Z0
...
```

## 不完整文件处理

如果最后一个 TIFF 文件的帧数少于预期（例如采集提前停止），转换器会：

- 截断到最大的 Z 切片整数倍
- 丢弃尾部不完整帧并给出警告
- 跳过滤帧数少于一个完整 Z volume 的文件

不会报错 — 转换将使用可用的完整 volumes 继续进行。

## 打包（Windows EXE）

使用 PyInstaller 创建独立的可执行文件：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name Tiff3D_Converter tiff3d_gui.py
```

将 `ImarisConvertBioformats` 放在可执行文件旁边的 `ImarisConvertBioformats/` 目录中以支持 IMS 输出。

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。

© 2026 Tom Wong - Tsinghua University. Powered by DeepSeek & Claude Code.
