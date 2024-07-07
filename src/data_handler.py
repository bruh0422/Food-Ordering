import json, os
from urllib.parse import parse_qs

def load_data(*file_path: tuple) -> dict:
    with open(os.path.join('data', *file_path), mode='r', encoding='utf8') as file:

        return json.load(file)

def write_data(data, *file_path: tuple) -> None:
    with open(os.path.join('data', *file_path), mode='w', encoding='utf8') as file:
        file.write(json.dumps(data, ensure_ascii=False, indent=4))

def parse_to_dict(parse) -> dict:
    data = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parse).items()}

    return data

def data_check():
    if not os.path.exists(os.path.join('data', 'system')):
        os.mkdir(os.path.join('data', 'system'))

    if not os.path.exists(os.path.join('data', 'system', 'nickname.json')):
        write_data({}, 'system', 'nickname.json')
    if not os.path.exists(os.path.join('data', 'system', 'order.json')):
        write_data(
        {
            'finished': {
                'accepted': {},
                'rejected': {},
            },
            'pending': {}
        },
        'system', 'order.json')
    if not os.path.exists(os.path.join('data', 'system', 'personnel.json')):
        write_data(
        {
            'admin': [],
            'staff': [],
            'student': []
        },
        'system', 'personnel.json')