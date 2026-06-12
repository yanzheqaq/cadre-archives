# -*- coding: utf-8 -*-
import os
import tempfile
import time
from typing import Dict, List, Optional


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


class ScannerError(RuntimeError):
    pass


class ScannerSettings:
    def __init__(
        self,
        device_id: str = "simulated_file_picker",
        dpi: int = 300,
        color_mode: str = "color",
        source: str = "flatbed",
        duplex: bool = False,
        use_driver_ui: bool = True,
        parent_window: int = 0,
    ):
        self.device_id = device_id
        self.dpi = int(dpi or 300)
        self.color_mode = color_mode or "color"
        self.source = source or "flatbed"
        self.duplex = bool(duplex)
        self.use_driver_ui = bool(use_driver_ui)
        self.parent_window = int(parent_window or 0)

    def to_dict(self) -> Dict[str, object]:
        return {
            "device_id": self.device_id,
            "dpi": self.dpi,
            "color_mode": self.color_mode,
            "source": self.source,
            "duplex": self.duplex,
            "use_driver_ui": self.use_driver_ui,
            "parent_window": self.parent_window,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, object]] = None):
        data = data or {}
        return cls(
            device_id=str(data.get("device_id") or "simulated_file_picker"),
            dpi=int(data.get("dpi") or 300),
            color_mode=str(data.get("color_mode") or "color"),
            source=str(data.get("source") or "flatbed"),
            duplex=bool(data.get("duplex", False)),
            use_driver_ui=bool(data.get("use_driver_ui", True)),
            parent_window=int(data.get("parent_window") or 0),
        )


class SimulatedScannerBackend:
    backend_id = "simulation"

    def list_devices(self) -> List[Dict[str, str]]:
        return [
            {
                "id": "simulated_file_picker",
                "name": "模拟扫描（选择图片）",
                "backend": self.backend_id,
            }
        ]

    def scan_selected_files(self, files: List[str], settings: Optional[ScannerSettings] = None) -> List[str]:
        out = []
        for path in files or []:
            abs_path = os.path.abspath(path)
            ext = os.path.splitext(abs_path)[1].lower()
            if os.path.isfile(abs_path) and ext in IMAGE_EXTENSIONS:
                out.append(abs_path)
        if not out:
            raise ScannerError("未选择可用的扫描图片")
        return out

    def scan_to_files(self, settings: Optional[ScannerSettings] = None, output_dir: str = "") -> List[str]:
        raise ScannerError("当前为模拟扫描后端，请在界面中选择图片作为扫描结果")


class TwainScannerBackend:
    backend_id = "twain"

    def __init__(self):
        self._twain = None
        self._import_error = None

    def _load_twain(self):
        if self._twain is not None:
            return self._twain
        try:
            import twain
        except Exception as e:
            self._import_error = e
            raise ScannerError("TWAIN 扫描库未安装，请在打包环境安装 pytwain。")
        self._twain = twain
        return twain

    def is_available(self) -> bool:
        try:
            self._load_twain()
            return True
        except Exception:
            return False

    def list_devices(self) -> List[Dict[str, str]]:
        twain = self._load_twain()
        sm = None
        try:
            sm = twain.SourceManager(0)
            return [
                {
                    "id": str(name),
                    "name": str(name),
                    "backend": self.backend_id,
                }
                for name in (sm.source_list or [])
            ]
        except Exception as e:
            raise ScannerError(f"读取 TWAIN 设备失败：{e}")
        finally:
            if sm is not None:
                try:
                    sm.close()
                except Exception:
                    pass

    def scan_selected_files(self, files: List[str], settings: Optional[ScannerSettings] = None) -> List[str]:
        return SimulatedScannerBackend().scan_selected_files(files, settings=settings)

    def scan_to_files(self, settings: Optional[ScannerSettings] = None, output_dir: str = "") -> List[str]:
        twain = self._load_twain()
        settings = settings or ScannerSettings()
        output_dir = output_dir or tempfile.mkdtemp(prefix="cadre_scan_")
        os.makedirs(output_dir, exist_ok=True)
        device_id = settings.device_id if settings.device_id != "simulated_file_picker" else None
        pixel_type = self._pixel_type(settings.color_mode)
        scanned = []
        created_paths = []

        def next_path():
            idx = len(scanned) + len(created_paths) + 1
            return os.path.join(output_dir, f"scan_{int(time.time())}_{idx:03d}.bmp")

        try:
            if hasattr(twain, "acquire_file"):
                path = next_path()
                info = twain.acquire_file(
                    path,
                    ds_name=device_id,
                    dpi=settings.dpi,
                    pixel_type=pixel_type,
                    parent_window=settings.parent_window,
                    show_ui=settings.use_driver_ui,
                    modal=True,
                )
                if info is None:
                    raise ScannerError("扫描已取消")
                if os.path.exists(path):
                    scanned.append(path)
            else:
                sm = twain.SourceManager(0)
                src = None
                try:
                    src = sm.open_source(device_id)
                    if src is None:
                        raise ScannerError("未选择扫描仪或扫描已取消")

                    def before():
                        path = next_path()
                        created_paths.append(path)
                        return path

                    def after(remaining):
                        return None

                    src.acquire_file(before=before, after=after, show_ui=settings.use_driver_ui, modal=True)
                    scanned.extend([p for p in created_paths if os.path.isfile(p)])
                finally:
                    if src is not None:
                        try:
                            src.close()
                        except Exception:
                            pass
                    try:
                        sm.close()
                    except Exception:
                        pass
        except ScannerError:
            raise
        except Exception as e:
            raise ScannerError(f"TWAIN 扫描失败：{e}")

        scanned = [p for p in scanned if os.path.exists(p)]
        if not scanned:
            raise ScannerError("扫描完成但未生成图片文件")
        return scanned

    @staticmethod
    def _pixel_type(color_mode: str) -> str:
        value = (color_mode or "").lower()
        if value in {"bw", "black_white", "blackwhite", "黑白"}:
            return "bw"
        if value in {"gray", "grey", "grayscale", "灰度"}:
            return "gray"
        return "color"


class ScannerService:
    def __init__(self, backend=None):
        self.twain_backend = TwainScannerBackend()
        self.simulated_backend = SimulatedScannerBackend()
        self.backend = backend or self.twain_backend

    def list_devices(self) -> List[Dict[str, str]]:
        devices = []
        try:
            devices.extend(self.twain_backend.list_devices())
        except Exception:
            pass
        devices.extend(self.simulated_backend.list_devices())
        return devices

    def scan_selected_files(self, files: List[str], settings: Optional[ScannerSettings] = None) -> List[str]:
        return self.simulated_backend.scan_selected_files(files, settings=settings)

    def scan_to_files(self, settings: Optional[ScannerSettings] = None, output_dir: str = "") -> List[str]:
        settings = settings or ScannerSettings()
        if settings.device_id == "simulated_file_picker":
            return self.simulated_backend.scan_to_files(settings=settings, output_dir=output_dir)
        return self.twain_backend.scan_to_files(settings=settings, output_dir=output_dir)

    def has_twain_device(self) -> bool:
        return any(d.get("backend") == TwainScannerBackend.backend_id for d in self.list_devices())


_default_scanner_service = None


def get_scanner_service() -> ScannerService:
    global _default_scanner_service
    if _default_scanner_service is None:
        _default_scanner_service = ScannerService()
    return _default_scanner_service
