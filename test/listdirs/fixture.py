from os import mkdir, path

CHUNK_SIZE = 4096

diff_definition = {
    'a': {
        'a.txt': lambda: b'',
        'c': {
            'c.txt': lambda: b''
        },
        'D': {
            'd.txt': lambda: (b'd' * CHUNK_SIZE) + b'd'
        },
        'e': {
            'f': {},
            'g': {
                'g.txt': lambda: b'g'
            },
            'h': {
                'h.txt': lambda: b'h'
            },
            'e.txt': lambda: b''
        }
    },
    'b': {
        'b.txt': lambda: b'',
        'c': {
            'c.txt': lambda: b''
        },
        'd': {
            'd.txt': lambda: (b'd' * CHUNK_SIZE) + b'd',
            'd.1.txt': lambda: (b'D' * CHUNK_SIZE) + b'D',
            'd.2.txt': lambda: (b'd' * CHUNK_SIZE) + b'D'
        },
        'e': {
            'f': {
                'f.txt': lambda: b''
            },
            'g': {
                'G.txt': lambda: b''
            },
            'h': {
                'h.txt': lambda: b'h'
            },
            'e.txt': lambda: b''
        }
    }
}

CUR_DIR = path.dirname(__file__)
ROOT_DIR = path.join(CUR_DIR, 'diffs')


def make(definition=diff_definition, root_dir=ROOT_DIR):
    if not path.exists(root_dir):
        mkdir(root_dir, 0o755)

    for k, v in definition.items():
        file_path = path.join(root_dir, k)
        if isinstance(v, dict):
            make(v, file_path)
        else:
            with open(file_path, 'bw') as open_file:
                open_file.write(v())
