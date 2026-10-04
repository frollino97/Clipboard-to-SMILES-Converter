import csv
import hashlib
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import torch
from PIL import Image, ImageGrab
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)
from rdkit import Chem
from rdkit.Chem import AllChem
from molscribe import MolScribe
import selfies as sf

from converter import Converter
from model_utils import find_molscribe_checkpoint
from utils import smiles_to_molecular_properties


APP_NAME = "Clipboard2Smiles"
ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home()))
DATA_ROOT = LOCAL_APP_DATA / APP_NAME
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
LOGGER = logging.getLogger(APP_NAME)


class WindowsClipboardApp:
    def __init__(self):
        self.data_root = DATA_ROOT
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.image_input_dir = self.data_root / "image_queue"
        self.image_generated_dir = self.data_root / "image_generated"
        self.image_output_dir = self.data_root / "image_output"
        self.csv_file_path = self.data_root / "smiles.csv"
        for directory in (
            self.image_input_dir,
            self.image_generated_dir,
            self.image_output_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        legacy_history = ROOT / "smiles.csv"
        if not self.csv_file_path.exists() and legacy_history.exists():
            shutil.copy2(legacy_history, self.csv_file_path)
        if not self.csv_file_path.exists():
            with self.csv_file_path.open("w", newline="", encoding="utf-8") as history:
                csv.writer(history).writerow(["smiles", "image_file", "date"])

        self.model_path = find_molscribe_checkpoint(RESOURCE_ROOT)

        self.model = MolScribe(str(self.model_path), device=torch.device("cpu"))
        self.converter = Converter(
            model=self.model,
            image_input_dir=self.image_input_dir,
            image_generated_dir=self.image_generated_dir,
            notification_callback=self.notify,
        )
        self.length_history = 8
        self.max_n_images = 25
        self.last_clipboard_key = None
        self.last_queued_image_hash = None
        self.purchase_link = None

        self.tray = QSystemTrayIcon(
            QIcon(str(RESOURCE_ROOT / "pictograms" / "carlos_helper_logo.png"))
        )
        self.tray.setToolTip(APP_NAME)
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self._create_menu()

        self.window = QMainWindow()
        self.window.setWindowTitle(APP_NAME)
        self.window.setWindowIcon(
            QIcon(str(RESOURCE_ROOT / "pictograms" / "carlos_helper_logo.png"))
        )
        self.window.resize(420, 150)
        self.window.setCentralWidget(
            QLabel(
                "Clipboard2Smiles is running.\n\n"
                "Use the menu above or right-click the tray icon to convert "
                "clipboard content, watch the clipboard, or process queued images."
            )
        )
        self.window.menuBar().addMenu(self.menu)
        self.window.show()
        self.tray.show()
        self.tray.showMessage(
            APP_NAME,
            "Ready. Right-click the tray icon to open the menu.",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

        self.watch_timer = QTimer()
        self.watch_timer.setInterval(500)
        self.watch_timer.timeout.connect(self._watch_clipboard)
        self.queue_timer = QTimer()
        self.queue_timer.setInterval(500)
        self.queue_timer.timeout.connect(self._save_clipboard_image)
        self.update_history_menu()
        LOGGER.info("Clipboard2Smiles started; tray visible: %s", self.tray.isVisible())

    def _create_menu(self):
        for label, output_format in (
            ("Convert Clipboard to SMILES", "smiles"),
            ("Convert Clipboard to Image", "image"),
            ("Convert Clipboard to CAS", "cas"),
            ("Convert Clipboard to IUPAC", "iupac"),
            ("Convert Clipboard to InChI", "inchi"),
            ("Convert Clipboard to RDKit Mol", "mol"),
            ("Convert Clipboard to SELFIES", "selfies"),
        ):
            self._add_conversion_action(self.menu, label, output_format)

        self.menu.addSeparator()
        operations = self.menu.addMenu("Clipboard SMILES Operations")
        for label, output_format in (
            ("Canonicalize SMILES", "canonicalize"),
            ("Augment SMILES", "augment"),
            ("Remove Atom Mapping", "remove_atom_mapping"),
        ):
            self._add_conversion_action(operations, label, output_format)

        self.menu.addSeparator()
        self._add_conversion_action(self.menu, "Convert Clipboard to Price", "price")
        self.open_purchase_action = QAction("Open Last Product Link", self.menu)
        self.open_purchase_action.setEnabled(False)
        self.open_purchase_action.triggered.connect(self.open_purchase_link)
        self.menu.addAction(self.open_purchase_action)

        self.menu.addSeparator()
        self.watch_action = QAction("Watch Clipboard for Molecules", self.menu)
        self.watch_action.triggered.connect(self.toggle_clipboard_watching)
        self.menu.addAction(self.watch_action)
        self.queue_watch_action = QAction("Start Clipboard Image Collection", self.menu)
        self.queue_watch_action.triggered.connect(self.toggle_image_collection)
        self.menu.addAction(self.queue_watch_action)
        self.menu.addAction("Process Image Queue", self.batch_images_to_smiles)
        self.menu.addAction("Open Image Queue", self.open_queue_folder)

        self.menu.addSeparator()
        self.history_smiles_menu = self.menu.addMenu("Copy SMILES from History")
        self.history_structures_menu = self.menu.addMenu("Copy Structure from History")
        self.history_properties_menu = self.menu.addMenu(
            "Molecular Properties from History"
        )
        self.history_prices_menu = self.menu.addMenu("Find Price from History")
        self.menu.addAction("Open History File", self.open_history_file)

        options = self.menu.addMenu("Options")
        vendors = options.addMenu("Select Vendor")
        vendor_group = QActionGroup(vendors)
        vendor_group.setExclusive(True)
        for label, vendor_name in (
            ("Enamine", "Enamine"),
            ("Chemie Brunschwieg", "ChemieBrunschwieg"),
        ):
            action = QAction(label, vendors)
            action.setCheckable(True)
            action.setChecked(vendor_name == "Enamine")
            action.triggered.connect(
                lambda checked=False, name=vendor_name: self.select_vendor(name)
            )
            vendor_group.addAction(action)
            vendors.addAction(action)

        share_text = (
            "Clipboard-to-SMILES-Converter: convert molecular structures "
            "directly from the clipboard."
        )
        share_url = "https://twitter.com/intent/tweet?text=" + quote(share_text)
        options.addAction(
            "Share the App",
            lambda checked=False: self.open_url(share_url),
        )
        options.addAction(
            "Credits & Updates",
            lambda checked=False: self.open_url(
                "https://github.com/O-Schilter/Clipboard-to-SMILES-Converter"
            ),
        )
        options.addSeparator()
        options.addAction(
            "Quit", lambda checked=False: QApplication.instance().quit()
        )

    def _add_conversion_action(self, menu, label, output_format):
        action = QAction(label, menu)
        action.triggered.connect(
            lambda checked=False, fmt=output_format: self.clipboard_to(fmt)
        )
        menu.addAction(action)
        return action

    def notify(self, title, subtitle, message):
        self.tray.showMessage(
            f"{title}: {subtitle}",
            message,
            QSystemTrayIcon.MessageIcon.Information,
            6000,
        )

    def _identify_clipboard_content(self):
        try:
            image = ImageGrab.grabclipboard()
        except (OSError, RuntimeError):
            LOGGER.exception("Could not read the Windows clipboard image.")
            image = None
        if isinstance(image, Image.Image):
            return {"format": "image", "content": image}

        text = QApplication.clipboard().text()
        if not text:
            return None
        if text.startswith("InChI="):
            try:
                if Chem.MolFromInchi(text) is not None:
                    return {"format": "inchi", "content": text}
            except ValueError:
                LOGGER.info("Clipboard text was not a valid InChI.")

        if text.count(">") == 2:
            try:
                if AllChem.ReactionFromSmarts(text) is not None:
                    return {"format": "smiles", "content": text}
            except ValueError:
                LOGGER.info("Clipboard text was not a valid reaction SMILES.")
        else:
            try:
                if Chem.MolFromSmiles(text) is not None:
                    return {"format": "smiles", "content": text}
            except ValueError:
                LOGGER.info("Clipboard text was not a valid SMILES.")

        try:
            if Chem.MolFromMolBlock(text) is not None:
                return {"format": "mol", "content": text}
        except ValueError:
            LOGGER.info("Clipboard text was not a valid MOL block.")
        try:
            if sf.decoder(text):
                return {"format": "selfies", "content": text}
        except (ValueError, IndexError):
            LOGGER.info("Clipboard text was not valid SELFIES.")

        input_format = "cas" if re.fullmatch(r"\d+-\d+-\d+", text.strip()) else "iupac"
        return {"format": input_format, "content": text}

    def _clipboard_key(self, clipboard_input):
        content = clipboard_input["content"]
        if clipboard_input["format"] == "image":
            image_bytes = BytesIO()
            content.convert("RGBA").save(image_bytes, format="PNG")
            digest = hashlib.sha256(image_bytes.getvalue()).hexdigest()
            return "image", digest
        return clipboard_input["format"], content

    def clipboard_to(self, output_format):
        clipboard_input = self._identify_clipboard_content()
        if clipboard_input is None:
            self.notify("No clipboard content", "", "Copy text or an image first.")
            return None
        try:
            output, smiles = self.converter.convert(
                clipboard_input["content"],
                clipboard_input["format"],
                output_format,
            )
        except (KeyError, OSError, RuntimeError, ValueError):
            LOGGER.exception("Clipboard conversion failed (%s).", output_format)
            self.notify("Conversion failed", output_format, "See the application log.")
            return None
        if not output:
            self.notify(
                "Conversion failed",
                output_format,
                f"No {output_format.upper()} result was found.",
            )
            return None

        input_key = self._clipboard_key(clipboard_input)
        if output_format == "price":
            self.purchase_link = output.get("link")
            self.open_purchase_action.setEnabled(bool(self.purchase_link))
            self.notify(
                f"Buy {output['item_name']}",
                f"{output['amount']} for {output['price']} CHF",
                f"{output['price_per']:.2f} CHF/g. Use 'Open Last Product Link'.",
            )
        elif output_format == "image":
            if not self.copy_image_to_clipboard(output):
                return None
            self.notify("Image copied to clipboard", "", str(output))
            if smiles:
                self.smiles_to_history(smiles)
        else:
            QApplication.clipboard().setText(str(output))
            if output_format in {
                "canonicalize",
                "augment",
                "remove_atom_mapping",
                "standardize",
            }:
                self.notify(
                    f"{output_format.replace('_', ' ').capitalize()} copied",
                    "",
                    str(output),
                )
            else:
                self.notify(f"{output_format.upper()} copied to clipboard", "", str(output))
                if smiles:
                    self.smiles_to_history(smiles)

        if output_format == "price":
            self.last_clipboard_key = input_key
        elif output_format != "image":
            detected_output = self._identify_clipboard_content()
            self.last_clipboard_key = (
                self._clipboard_key(detected_output)
                if detected_output is not None
                else ("text", str(output))
            )
        return output

    def copy_image_to_clipboard(self, image_path):
        try:
            with Image.open(image_path) as image:
                rgba = image.convert("RGBA")
                raw = rgba.tobytes()
                encoded = BytesIO()
                rgba.save(encoded, format="PNG")
                qimage = QImage(
                    raw,
                    rgba.width,
                    rgba.height,
                    rgba.width * 4,
                    QImage.Format.Format_RGBA8888,
                ).copy()
            QApplication.clipboard().setImage(qimage)
            self.last_clipboard_key = (
                "image",
                hashlib.sha256(encoded.getvalue()).hexdigest(),
            )
            return True
        except (OSError, ValueError):
            LOGGER.exception("Could not copy generated image to clipboard.")
            self.notify("Image copy failed", "", str(image_path))
            return False

    def toggle_clipboard_watching(self, checked=False):
        if self.watch_timer.isActive():
            self.watch_timer.stop()
            self.watch_action.setText("Watch Clipboard for Molecules")
        else:
            self.last_clipboard_key = None
            self.watch_timer.start()
            self.watch_action.setText("Stop Watching Clipboard")

    def _watch_clipboard(self):
        clipboard_input = self._identify_clipboard_content()
        if clipboard_input is None:
            return
        key = self._clipboard_key(clipboard_input)
        if key == self.last_clipboard_key:
            return
        self.last_clipboard_key = key
        try:
            output, _ = self.converter.convert(
                clipboard_input["content"], clipboard_input["format"], "smiles"
            )
        except (KeyError, OSError, RuntimeError, ValueError):
            LOGGER.exception("Clipboard watcher conversion failed.")
            return
        if output:
            QApplication.clipboard().setText(str(output))
            self.last_clipboard_key = ("smiles", str(output))
            self.smiles_to_history(str(output))
            self.notify("Molecule detected", "SMILES copied", str(output))

    def toggle_image_collection(self, checked=False):
        if self.queue_timer.isActive():
            self.queue_timer.stop()
            self.queue_watch_action.setText("Start Clipboard Image Collection")
            self.batch_images_to_smiles()
        else:
            self.last_queued_image_hash = None
            self.queue_timer.start()
            self.queue_watch_action.setText("Stop Clipboard Image Collection")
            self.notify("Image collection started", "", "Copy images to add them to the queue.")

    def _save_clipboard_image(self):
        try:
            image = ImageGrab.grabclipboard()
        except (OSError, RuntimeError):
            LOGGER.exception("Could not read image during clipboard collection.")
            return
        if not isinstance(image, Image.Image):
            return
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        digest = hashlib.sha256(image_bytes).hexdigest()
        if digest == self.last_queued_image_hash:
            return
        filename = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "_clipboard.png"
        try:
            (self.image_input_dir / filename).write_bytes(image_bytes)
        except OSError:
            LOGGER.exception("Could not add clipboard image to the queue.")
            self.notify("Image queue save failed", "", str(self.image_input_dir))
            return
        self.last_queued_image_hash = digest

    def batch_images_to_smiles(self, checked=False):
        image_paths = sorted(
            path for path in self.image_input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        converted = 0
        for image_path in image_paths:
            try:
                smiles = self.converter.image_to_smiles(
                    image_path, image_or_path="path"
                )
            except (OSError, RuntimeError, ValueError):
                LOGGER.exception("Could not process queued image %s.", image_path)
                continue
            if smiles:
                self.smiles_to_history(smiles)
                converted += 1
        self.notify(
            "Image queue processed",
            f"{converted} molecule(s) recognized",
            f"Processed {len(image_paths)} image(s). Unrecognized images remain in the queue.",
        )

    def _read_all_history(self):
        try:
            with self.csv_file_path.open(
                newline="", encoding="utf-8-sig"
            ) as history_file:
                reader = csv.DictReader(history_file)
                rows = []
                for row in reader:
                    normalized = {
                        (key or "").strip().lower(): value or ""
                        for key, value in row.items()
                    }
                    smiles = normalized.get("smiles", "").strip()
                    image_file = normalized.get("image_file", "False").strip() or "False"
                    date = normalized.get("date", "").strip()
                    if smiles:
                        rows.append((smiles, image_file, date))
                return rows
        except (OSError, UnicodeError, csv.Error):
            LOGGER.exception("Could not read the molecule history.")
            return []

    def smiles_to_history(self, smiles):
        image_filename = "False"
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            image_path = self.converter.smiles_to_image(smiles)
            if image_path:
                image_filename = Path(image_path).name
        except (OSError, RuntimeError, ValueError):
            LOGGER.exception("Could not render history image for %s.", smiles)

        entries = [
            row for row in self._read_all_history() if row[0] != smiles
        ]
        entries.append((smiles, image_filename, date))
        temporary_file = self.csv_file_path.with_suffix(".tmp")
        try:
            with temporary_file.open("w", newline="", encoding="utf-8") as history_file:
                writer = csv.writer(history_file)
                writer.writerow(["smiles", "image_file", "date"])
                writer.writerows(entries)
            temporary_file.replace(self.csv_file_path)
        except OSError:
            LOGGER.exception("Could not write molecule history.")
            self.notify("History save failed", "", str(self.csv_file_path))
            return
        self.update_history_menu()
        self.remove_over_max_images()

    def update_history_menu(self):
        for menu in (
            self.history_smiles_menu,
            self.history_structures_menu,
            self.history_properties_menu,
            self.history_prices_menu,
        ):
            menu.clear()
        entries = self._read_all_history()[-self.length_history:]
        for smiles, _image_file, _date in reversed(entries):
            self.history_smiles_menu.addAction(
                smiles, lambda checked=False, value=smiles: self.copy_text(value)
            )

            structure_menu = self.history_structures_menu.addMenu(smiles)
            for label, output_format in (
                ("SMILES", "smiles"),
                ("CAS", "cas"),
                ("IUPAC", "iupac"),
                ("InChI", "inchi"),
                ("RDKit Mol", "mol"),
                ("SELFIES", "selfies"),
                ("Image", "image"),
            ):
                structure_menu.addAction(
                    label,
                    lambda checked=False, molecule=smiles, fmt=output_format:
                        self.convert_history_item(molecule, fmt),
                )

            properties_menu = self.history_properties_menu.addMenu(smiles)
            properties = smiles_to_molecular_properties(smiles)
            if properties:
                for name, value in properties.items():
                    properties_menu.addAction(
                        f"{name}: {value:.3f}",
                        lambda checked=False, number=value: self.copy_text(str(number)),
                    )
            self.history_prices_menu.addAction(
                smiles,
                lambda checked=False, molecule=smiles:
                    self.convert_history_item(molecule, "price"),
            )

    def convert_history_item(self, smiles, output_format):
        try:
            output, _ = self.converter.convert(smiles, "smiles", output_format)
        except (KeyError, OSError, RuntimeError, ValueError):
            LOGGER.exception("History conversion failed (%s).", output_format)
            self.notify("Conversion failed", output_format, smiles)
            return
        if not output:
            self.notify("Conversion failed", output_format, smiles)
            return
        if output_format == "price":
            self.purchase_link = output.get("link")
            self.open_purchase_action.setEnabled(bool(self.purchase_link))
            self.notify(
                f"Buy {output['item_name']}",
                f"{output['amount']} for {output['price']} CHF",
                f"{output['price_per']:.2f} CHF/g. Use 'Open Last Product Link'.",
            )
        elif output_format == "image":
            if self.copy_image_to_clipboard(output):
                self.notify("Image copied to clipboard", "", str(output))
        else:
            self.copy_text(str(output))
            self.notify(f"{output_format.upper()} copied to clipboard", "", str(output))

    def copy_text(self, text):
        QApplication.clipboard().setText(text)

    def remove_over_max_images(self):
        for directory in (self.image_output_dir, self.image_generated_dir):
            files = sorted(directory.glob("*.png"), key=lambda item: item.stat().st_mtime)
            for old_file in files[:-self.max_n_images]:
                try:
                    old_file.unlink()
                except OSError:
                    LOGGER.exception("Could not remove old image %s.", old_file)

    def select_vendor(self, vendor_name):
        self.converter.vendors.select_vendor(vendor_name)

    def open_history_file(self, checked=False):
        try:
            os.startfile(self.csv_file_path)
        except OSError:
            LOGGER.exception("Could not open history file.")
            self.notify("Could not open history", "", str(self.csv_file_path))

    def open_queue_folder(self, checked=False):
        try:
            os.startfile(self.image_input_dir)
        except OSError:
            LOGGER.exception("Could not open image queue.")
            self.notify("Could not open image queue", "", str(self.image_input_dir))

    def open_purchase_link(self, checked=False):
        self.open_url(self.purchase_link)

    @staticmethod
    def open_url(url):
        if url:
            QDesktopServices.openUrl(QUrl(url))


def main():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=DATA_ROOT / "clipboard2smiles.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    application = QApplication(sys.argv)
    application.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            APP_NAME,
            "Windows system tray is unavailable. The app cannot display its menu.",
        )
        return 1
    try:
        _clipboard_app = WindowsClipboardApp()
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        LOGGER.exception("Could not start Clipboard2Smiles.")
        QMessageBox.critical(
            None,
            APP_NAME,
            "The application could not start. Check the model files and log in "
            f"{DATA_ROOT}.",
        )
        return 1
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
