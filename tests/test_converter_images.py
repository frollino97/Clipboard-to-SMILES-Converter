import tempfile
import unittest
from pathlib import Path

from PIL import Image

from converter import Converter


class FakeModel:
    def predict_image_file(self, image_path, **kwargs):
        if not Path(image_path).is_file():
            raise FileNotFoundError(image_path)
        return {"smiles": "CCO", "confidence": 0.99}


class ConverterImageTests(unittest.TestCase):
    def test_path_input_is_preserved_and_clipboard_temp_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "queue"
            generated_dir = root / "generated"
            converter = Converter(FakeModel(), input_dir, generated_dir)

            queued_image = input_dir / "queued.png"
            Image.new("RGB", (3, 3), "white").save(queued_image)
            self.assertEqual(
                converter.image_to_smiles(queued_image, image_or_path="path"),
                "CCO",
            )
            self.assertTrue(queued_image.exists())

            self.assertEqual(
                converter.image_to_smiles(Image.new("RGB", (3, 3), "white")),
                "CCO",
            )
            self.assertEqual(list(input_dir.glob("tmp*.png")), [])

    def test_smiles_image_generation_uses_rdkit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = Converter(FakeModel(), root / "queue", root / "generated")
            image_path = converter.smiles_to_image("CCO")
            self.assertTrue(Path(image_path).is_file())
            with Image.open(image_path) as image:
                self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
