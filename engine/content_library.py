"""Local, versioned original-character library. Never uploads or clones a real person."""
from pathlib import Path
import json
import re
import shutil
import hashlib
import uuid

from PIL import Image
from .production import save, read, digest


class CharacterLibrary:
    def __init__(self, root='data/content/characters'):
        self.root = Path(root).resolve()

    def _folder(self, identifier):
        if not re.fullmatch(r'[a-z0-9-]{1,80}', str(identifier)):
            raise ValueError('Invalid character ID')
        return self.root / identifier

    def create(self, name, description, *, reference_files=(), original_confirmed=False):
        if original_confirmed is not True:
            raise ValueError('Confirm this is your original/authorized fictional character; no impersonation')
        if not str(name).strip() or len(str(description).strip()) < 20:
            raise ValueError('Give the character a name and a detailed original physical description')
        identifier = re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')[:45] or 'character'
        identifier += '-' + uuid.uuid4().hex[:8]
        folder = self._folder(identifier)
        records = []
        # Validate every supplied image before creating a library entry.
        for filename in reference_files:
            path = Path(filename).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                raise ValueError('Character references must be local PNG/JPEG/WebP images')
            if path.stat().st_size > 20*1024*1024:
                raise ValueError('Character reference exceeds 20 MB')
            with Image.open(path) as im:
                im.verify()
            records.append((path, digest(path)))
        folder.mkdir(parents=True)
        refs = []
        for source, sha in records:
            target = folder / (sha + source.suffix.lower())
            shutil.copy2(source, target)
            refs.append({'path':str(target), 'sha256':sha})
        value = {'schema_version':1, 'id':identifier, 'name':str(name).strip(),
                 'description':str(description).strip(), 'original_confirmed':True,
                 'references':refs, 'version':1, 'type':'original-fictional-character'}
        save(folder/'character.json', value)
        return value

    def get(self, identifier):
        value = read(self._folder(identifier)/'character.json')
        if not value:
            raise ValueError('Character not found')
        for reference in value['references']:
            path = Path(reference['path']).resolve()
            if not path.is_relative_to(self._folder(identifier)) or digest(path) != reference['sha256']:
                raise ValueError('Character reference is outside the library or changed; reapprove it')
        return value

    def list(self):
        if not self.root.exists():
            return []
        return [self.get(p.parent.name) for p in sorted(self.root.glob('*/character.json'))]


def character_snapshot(character):
    """Provider-neutral identity contract, retained with each project."""
    return {'id':character['id'], 'version':character['version'], 'name':character['name'],
            'canonical':character['description'], 'references':character['references'],
            'sha256':hashlib.sha256(json.dumps(character, sort_keys=True).encode()).hexdigest()}
