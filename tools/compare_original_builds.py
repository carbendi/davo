"""Compare original build artifacts as data; never execute their contents."""
import hashlib, io, json, marshal, struct, zipfile, zlib
from pathlib import Path

def sha(data):
    return hashlib.sha256(data).hexdigest()

def sections(data):
    pe = struct.unpack_from('<I', data, 60)[0]
    count = struct.unpack_from('<H', data, pe + 6)[0]
    opt_size = struct.unpack_from('<H', data, pe + 20)[0]
    opt = pe + 24
    result = {}
    for i in range(count):
        off = opt + opt_size + i * 40
        name = data[off:off+8].rstrip(b'\0').decode('ascii')
        size, pointer = struct.unpack_from('<II', data, off + 16)
        result[name] = {'size': size, 'sha256': sha(data[pointer:pointer+size])}
    security_offset = opt + (112 if struct.unpack_from('<H', data, opt)[0] == 0x20b else 96) + 8 * 4
    cert_address, cert_size = struct.unpack_from('<II', data, security_offset)
    return {'sections': result, 'authenticode_certificate_size': cert_size}

def carchive(data):
    cookie = data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
    magic, length, toc_off, toc_len, version, library = struct.unpack_from('!8sIIII64s', data, cookie)
    start = cookie + 88 - length
    toc = data[start+toc_off:start+toc_off+toc_len]
    entries = {}
    pos = 0
    while pos < len(toc):
        entry_len, offset, compressed, uncompressed, flag, kind = struct.unpack_from('!iIIIBc', toc, pos)
        name = toc[pos+18:pos+entry_len].rstrip(b'\0').decode('utf-8')
        content = data[start+offset:start+offset+compressed]
        entries[name] = zlib.decompress(content) if flag else content
        pos += entry_len
    return entries

def pyz_modules(data):
    toc_offset = struct.unpack_from('!i', data, 8)[0]
    toc = dict(marshal.loads(data[toc_offset:]))
    result = {}
    for name, (kind, offset, size) in toc.items():
        result[name] = sha(data[offset:offset+size])
    return result

def package(folder):
    nested = next(Path(folder).rglob('SpeedEditorCustomizer-Windows.zip'))
    raw = nested.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files = {n.replace('\\','/'): z.read(n) for n in z.namelist() if not n.endswith('/')}
    exe_name = next(n for n in files if n.endswith('/SpeedEditorCustomizer.exe'))
    deps_name = next(n for n in files if n.endswith('/build-dependencies.txt'))
    deps = {}
    for line in files[deps_name].decode('utf-8-sig').splitlines():
        if '==' in line:
            name, version = line.split('==', 1)
            deps[name.lower()] = version
    exe = files[exe_name]
    entries = carchive(exe)
    pyz = next(value for name, value in entries.items() if name.lower().endswith('.pyz'))
    return {'zip_sha256': sha(raw), 'zip_size':len(raw), 'exe_sha256':sha(exe),
            'exe_size': len(exe), 'pe': sections(exe),
            'files': {n:sha(v) for n,v in files.items()}, 'dependencies':deps,
            'archive': {n:sha(v) for n,v in entries.items()}, 'modules':pyz_modules(pyz)}

def diff(a, b):
    return {'added':sorted(b.keys()-a.keys()), 'removed':sorted(a.keys()-b.keys()),
            'changed':{k:{'old':a[k], 'new':b[k]} for k in sorted(a.keys()&b.keys()) if a[k]!=b[k]},
            'identical_count':sum(a[k]==b[k] for k in a.keys()&b.keys())}

old, new = package('comparison/old'), package('comparison/new')
report = {'old': {k:v for k,v in old.items() if k not in ('files','dependencies','archive','modules')},
          'new': {k:v for k,v in new.items() if k not in ('files','dependencies','archive','modules')},
          'dependencies':diff(old['dependencies'],new['dependencies']),
          'files':diff(old['files'],new['files']),
          'embedded_entries':diff(old['archive'],new['archive']),
          'embedded_modules':diff(old['modules'],new['modules'])}
Path('comparison-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
