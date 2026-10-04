import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from rdkit import Chem

from model_utils import find_molscribe_checkpoint
from smiles_operations import (
    augment_smiles,
    canonicalize_smiles,
    remove_atom_mapping,
)


class SmilesOperationsTests(unittest.TestCase):
    def test_canonicalizes_smiles(self):
        self.assertEqual(canonicalize_smiles("OCC"), "CCO")

    def test_canonicalizes_reaction_with_empty_agents(self):
        self.assertEqual(canonicalize_smiles("CCO>>CC=O"), "CCO>>CC=O")

    def test_invalid_smiles_returns_none(self):
        self.assertIsNone(canonicalize_smiles("not smiles"))

    def test_removes_atom_mapping_including_wildcards(self):
        self.assertEqual(
            remove_atom_mapping("[CH3:1][*:2]"),
            "[CH3][*]",
        )

    def test_augments_reaction_with_empty_agent_section(self):
        augmented = augment_smiles("CCO>>CC=O")
        self.assertIsNotNone(augmented)
        self.assertEqual(len(augmented.split(">")), 3)
        self.assertEqual(augmented.split(">")[1], "")
        self.assertIsNotNone(Chem.MolFromSmiles(augmented.split(">")[0]))
        self.assertIsNotNone(Chem.MolFromSmiles(augmented.split(">")[2]))

    def test_checkpoint_lookup_uses_huggingface_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource_root = root / "app"
            checkpoint = (
                root
                / "hub"
                / "models--yujieq--MolScribe"
                / "snapshots"
                / "snapshot"
                / "swin_base_char_aux_1m.pth"
            )
            checkpoint.parent.mkdir(parents=True)
            checkpoint.touch()
            with patch.dict(os.environ, {"HF_HUB_CACHE": str(root / "hub")}):
                self.assertEqual(
                    find_molscribe_checkpoint(resource_root),
                    checkpoint,
                )


if __name__ == "__main__":
    unittest.main()
