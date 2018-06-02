from os import mkdir, path


diff_definition = {
    'a': {
        'a.txt': lambda: b'',
        'c': {
            'c.txt': lambda: b''
        },
        'd': {
            'd.txt': lambda: (b'd' * 4096) + b'd'
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
            'd.txt': lambda: (b'd' * 4096) + b'd',
            'd.1.txt': lambda: (b'D' * 4096) + b'D',
            'd.2.txt': lambda: (b'd' * (4096)) + b'D'
        },
        'e': {
            'f': {
                'f.txt': lambda: b''
            },
            'g': {
                'g.txt': lambda: b''
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


if __name__ == '__main__':
    make()
