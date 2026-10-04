import tempfile
import torch
from pathlib import Path
from collections.abc import Callable


import selfies as sf
from rdkit import Chem
from rdkit.Chem import Draw
from smiles_operations import augment_smiles, canonicalize_smiles, remove_atom_mapping

from utils import create_filename_from_smiles
from api_conversions import smiles_to_cas_api, smiles_to_iupac_api, iupac_to_smiles_api, cas_to_smiles_api
from vendors import Vendors, Enamine, ChemieBrunschwieg


class Converter():
    def __init__(
        self,
        model,
        image_input_dir,
        image_generated_dir,
        notification_callback: Callable[[str, str, str], None] | None = None,
    ):
        self.model = model
        self.image_input_dir = image_input_dir
        self.image_generated_dir = image_generated_dir
        self.notification_callback = notification_callback
        self.image_input_dir.mkdir(parents=True, exist_ok=True)
        self.image_generated_dir.mkdir(parents=True, exist_ok=True)
        self.image_confidence_level = 0.66

        self.vendors = Vendors([Enamine(), ChemieBrunschwieg()])

        self.conversion_to_smiles = {
            'cas': self.cas_to_smiles,
            'iupac': self.iupac_to_smiles,
            'image': self.image_to_smiles,
            'smiles': self.smiles_to_smiles,
            'inchi': self.inchi_to_smiles,
            'mol': self.mol_to_smiles,
            'selfies': self.selfies_to_smiles,
        }
        self.conversion_from_smiles = {
            'cas': self.smiles_to_cas,
            'iupac': self.smiles_to_iupac,
            'image': self.smiles_to_image,
            'smiles': self.smiles_to_smiles,
            'price': self.smiles_to_price,
            'inchi': self.smiles_to_inchi,
            'mol': self.smiles_to_mol,
            'selfies': self.smiles_to_selfies,
            'remove_atom_mapping': self.smiles_remove_atom_mapping,
            'canonicalize': self.smiles_canonicalize,
            'standardize': self.smiles_standardize,
            'augment': self.smiles_augment,
        }

    def convert(self, content, input_format, output_format):
        smiles = self.conversion_to_smiles[input_format](content)
        if smiles:
            output = self.conversion_from_smiles[output_format](smiles)
        else:
            output = False
        return output, smiles

    # to SMILES conversions
    def cas_to_smiles(self, cas):
        try:
            smiles = cas_to_smiles_api(cas)
            return smiles
        except:
            return False

    def iupac_to_smiles(self, iupac):
        try:
            smiles = iupac_to_smiles_api(iupac)
            return smiles
        except:
            return False

    def image_to_smiles(self, image, image_or_path='image'):
        temporary_file = None
        if image_or_path == 'image':
            with tempfile.NamedTemporaryFile(
                    suffix=".png", dir=self.image_input_dir, delete=False) as temp_file:
                temporary_file = Path(temp_file.name)
            file_path = temporary_file
        else:
            file_path = Path(image)

        try:
            if temporary_file is not None:
                image.save(temporary_file, "PNG")
            with torch.no_grad():
                output = self.model.predict_image_file(
                    str(file_path), return_atoms_bonds=False, return_confidence=True)
            smiles = output['smiles']
            confidence = output['confidence']
        finally:
            if temporary_file is not None:
                temporary_file.unlink(missing_ok=True)

        if confidence > self.image_confidence_level:
            return smiles
        if self.notification_callback is not None:
            self.notification_callback(
                "Low-confidence structure",
                "Retake screenshot",
                f"Confidence below {self.image_confidence_level:.2f}. Proposed SMILES: {smiles}",
            )
        return False

    def smiles_to_smiles(self, smiles):
        return smiles

    def inchi_to_smiles(self, inchi):
        try:
            mol = Chem.MolFromInchi(inchi)
            if mol is None:
                return False
            return Chem.MolToSmiles(mol)
        except:
            return False

    def mol_to_smiles(self, mol):
        try:
            molecule = Chem.MolFromMolBlock(mol)
            if molecule is None:
                return False
            return Chem.MolToSmiles(molecule)

        except:
            return False

    def selfies_to_smiles(self, selfies):
        try:
            smiles = sf.decoder(selfies)
            return smiles
        except:
            return False

    # from SMILES conversions
    def smiles_to_cas(self, smiles):
        try:
            cas = smiles_to_cas_api(smiles)
            return cas
        except:
            return False

    def smiles_to_iupac(self, smiles):
        try:
            iupac = smiles_to_iupac_api(smiles)
            return iupac
        except:
            return False

    def smiles_to_image(self, smiles):
        file_name, _ = create_filename_from_smiles(smiles)
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            return False
        image_path = self.image_generated_dir / file_name
        Draw.MolToFile(molecule, str(image_path), imageType="png")
        return image_path

    def smiles_to_price(self, smiles):
        cas = self.smiles_to_cas(smiles)
        if cas:
            price_dict = self.vendors.cas_to_price(cas)
            return price_dict

    def smiles_to_selfies(self, smiles):
        try:
            selfies = sf.encoder(smiles)
            return selfies
        except:
            return False

    def smiles_to_mol(self, smiles):
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False
            mol_string = Chem.MolToMolBlock(mol)
            return mol_string
        except:
            return False

    def smiles_to_inchi(self, smiles):
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False
            inchi = Chem.MolToInchi(mol)
            return inchi
        except:
            return False

    # SMILES to SMILES conversions

    def smiles_remove_atom_mapping(self, smiles):
        try:
            return remove_atom_mapping(smiles)
        except:
            return False

    def smiles_canonicalize(self, smiles):
        return canonicalize_smiles(smiles)

    def smiles_standardize(self, smiles):
        try:
            return smiles
        except:
            return False

    def smiles_augment(self, smiles):
        try:
            return augment_smiles(smiles)
        except:
            return False
