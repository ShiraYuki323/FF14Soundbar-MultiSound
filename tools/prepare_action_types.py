"""Regenerate the offline icon/action index from the FF14 7.05 Action sheet."""
import csv
import io
import json
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen

REVISION = 'c83b4538aca65f6e5aaf9d05523e755f8f1dc965'
SOURCE = f'https://github.com/xivapi/ffxiv-datamining/blob/{REVISION}/csv/Action.csv'
RAW = f'https://raw.githubusercontent.com/xivapi/ffxiv-datamining/{REVISION}/csv/'


def load_sheet(name):
    with urlopen(RAW + name + '.csv', timeout=25) as response:
        return list(csv.reader(io.StringIO(response.read().decode('utf-8-sig'), newline='')))


def generate(output):
    categories = {name: int(key) for key, name in load_sheet('ActionCategory')[3:] if name}
    rows = load_sheet('Action')
    icon, category, player, name = (rows[1].index(field) for field in
                                    ('Icon', 'ActionCategory', 'IsPlayerAction', 'Name'))
    grouped = defaultdict(set)
    for row in rows[3:]:
        if row[player] == 'True' and row[name] and int(row[icon]):
            grouped[int(row[icon])].add(int(row[category]))
    gcd = {categories['Spell'], categories['Weaponskill']}
    data = {
        'ability': sorted(key for key, types in grouped.items() if types == {categories['Ability']}),
        'gcd': sorted(key for key, types in grouped.items() if types <= gcd),
    }
    with output.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('{\n  "source": ' + json.dumps(SOURCE) + ',\n  "patch": "7.05",\n')
        for i, (label, ids) in enumerate(data.items()):
            stream.write(f'  "{label}": [\n')
            lines = [', '.join(map(str, ids[j:j+16])) for j in range(0,len(ids),16)]
            stream.write('    ' + ',\n    '.join(lines) + '\n  ]' + (',\n' if i == 0 else '\n'))
        stream.write('}\n')
    print(', '.join(f'{kind}: {len(ids)}' for kind, ids in data.items()))


if __name__ == '__main__':
    generate(Path(__file__).resolve().parents[1] / 'assets' / 'ff14-action-types.json')
