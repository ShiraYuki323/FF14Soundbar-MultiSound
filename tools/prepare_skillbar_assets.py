"""Build portable icon resources from the user's local FF14 asset pack."""
import argparse
import json
import shutil
import struct
from pathlib import Path

JOBS = [
    ('paladin','骑士','03 剑术师 骑士'), ('warrior','战士','05 斧术师 战士'),
    ('darkknight','暗黑骑士','14 黑骑'), ('gunbreaker','绝枪战士','19 绝枪'),
    ('whitemage','白魔法师','08 幻术师 白魔'), ('scholar','学者','11 学者'),
    ('astrologian','占星术士','15 占星'), ('sage','贤者','22 贤者'),
    ('monk','武僧','04 格斗家 武僧'), ('dragoon','龙骑士','06 枪术师 龙骑'),
    ('ninja','忍者','12 双剑师 忍者'), ('samurai','武士','16 武士'),
    ('reaper','钐镰客','21 镰刀'), ('viper','蝰蛇剑士','23 蝰蛇剑士'),
    ('bard','吟游诗人','07 弓箭手 诗人'), ('machinist','机工士','13 机工'),
    ('dancer','舞者','20 舞者'), ('blackmage','黑魔法师','09 咒术师 黑魔'),
    ('summoner','召唤师','10 秘术师 召唤'), ('redmage','赤魔法师','17 赤魔'),
    ('pictomancer','绘灵法师','24 绘灵法师'), ('bluemage','青魔法师','18 青魔'),
]


def prepare(source, destination):
    source, destination = Path(source), Path(destination)
    jobs = []
    for slug, name, folder in JOBS:
        target = destination / slug
        target.mkdir(parents=True, exist_ok=True)
        skills = []
        for path in sorted((source / '01 技能图标' / folder).glob('*.png')):
            with path.open('rb') as stream:
                header = stream.read(24)
            if header[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', header[16:24]) != (80, 80):
                continue
            shutil.copy2(path, target / path.name)
            skills.append(f'{slug}/{path.name}')
        icon = source / '03 职业图标' / '职业_透明底' / (slug + '.png')
        shutil.copy2(icon, target / 'job.png')
        jobs.append({'id': slug, 'name': name, 'image': f'{slug}/job.png', 'skills': skills})
    extras=[]
    target=destination/'role';target.mkdir(parents=True,exist_ok=True)
    for path in sorted((source/'01 技能图标'/'00 职能技能').rglob('*.png')):
        header=path.read_bytes()[:24]
        if header[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',header[16:24])==(80,80):
            shutil.copy2(path,target/path.name);extras.append('role/'+path.name)
    shutil.copy2(source / '06 HUD' / 'icona_frame_hr1.png', destination / 'frame.png')
    (destination / 'catalog.json').write_text(json.dumps({'jobs': jobs,'extras':sorted(set(extras))}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(jobs)} professions; {sum(len(job["skills"]) for job in jobs)} clear skills')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    prepare(args.source, args.destination)
