import re
from rdkit import Chem
from rdkit.Chem import AllChem
import random


def remove_atom_mapping(smiles: str) -> str:
    """
    Remove the atom mapping of a reaction SMILES.

    The resulting SMILES strings will still contain brackets and it may be
    advisable to canonicalize them or clean them up as a postprocessing step.

    Args:
        smiles: SMILES string potentially containing mapping information.

    Returns:
        A SMILES string without atom mapping information.
    """

    return re.sub(r":\d+(?=\])", "", smiles)


def canonicalize_smiles(smiles: str) -> str | None:
    """
    Canonicalizes a SMILES string.

    Args:
        smiles (str): The input SMILES string.

    Returns:
        str: The canonicalized SMILES string.

    """
    if smiles.count(">") == 2:
        try:
            reaction = AllChem.ReactionFromSmarts(smiles)
        except ValueError:
            return None
        if reaction is None or not reaction.GetReactants() or not reaction.GetProducts():
            return None

        reactant_smiles = ".".join(
            Chem.MolToSmiles(mol) for mol in reaction.GetReactants())
        agents_smiles = ".".join(
            Chem.MolToSmiles(mol) for mol in reaction.GetAgents())
        product_smiles = ".".join(
            Chem.MolToSmiles(mol) for mol in reaction.GetProducts())
        return ">".join((reactant_smiles, agents_smiles, product_smiles))

    mol = Chem.MolFromSmiles(smiles)
    if mol is not None:
        return Chem.MolToSmiles(mol)
    return None


def randomize_smiles(smiles, random_type="restricted", isomericSmiles=True):
    """
    From: https://github.com/undeadpixel/reinvent-randomized and https://github.com/GLambard/SMILES-X
    Returns a random SMILES given a SMILES of a molecule.
    :param mol: A Mol object
    :param random_type: The type (unrestricted, restricted, rotated) of randomization performed.
    :return : A random SMILES string of the same molecule or None if the molecule is invalid.
    """
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return None

    if random_type == "unrestricted":
        return Chem.MolToSmiles(mol, canonical=False, doRandom=True, isomericSmiles=isomericSmiles)
    elif random_type == "restricted":
        new_atom_order = list(range(mol.GetNumAtoms()))
        random.shuffle(new_atom_order)
        random_mol = Chem.RenumberAtoms(mol, newOrder=new_atom_order)
        return Chem.MolToSmiles(random_mol, canonical=False, isomericSmiles=isomericSmiles)
    elif random_type == 'rotated':
        n_atoms = mol.GetNumAtoms()
        rotation_index = random.randint(0, n_atoms-1)
        atoms = list(range(n_atoms))
        new_atoms_order = (atoms[rotation_index % len(
            atoms):]+atoms[:rotation_index % len(atoms)])
        rotated_mol = Chem.RenumberAtoms(mol, new_atoms_order)
        return Chem.MolToSmiles(rotated_mol, canonical=False, isomericSmiles=isomericSmiles)
    raise ValueError("Type '{}' is not valid".format(random_type))


def augment_smiles(smiles: str):
    """ Creates augmented SMILES string.

    Args:
        smiles (str): SMILES 

    Returns:
        str: augemented SMILES
    """
    if ">" not in smiles:
        return randomize_smiles(smiles)

    reaction_parts = smiles.split(">")
    if len(reaction_parts) != 3:
        return None

    randomized_parts = []
    for part in reaction_parts:
        if not part:
            randomized_parts.append("")
            continue
        randomized = randomize_smiles(part)
        if randomized is None:
            return None
        randomized_parts.append(randomized)
    return ">".join(randomized_parts)


augemnt_smiles = augment_smiles
