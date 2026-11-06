#!/usr/bin/env python3
"""Build the experimental video-ad loader guard APK from inputs you supply yourself.

    python3 -B build.py --original-apk YouTubeTV-2.07.02.apk --android-libs DIR \\
                        [--keystore KS --ks-pass-file FILE --key-alias ALIAS] [--diagnostic]

Nothing from Google is distributed with this project. You provide:

  --original-apk   the YouTube for Android TV 2.07.02 APK pulled from your own device
                   (`adb shell pm path com.google.android.youtube.tv`, then `adb pull`).
                   Its SHA-256 must equal ORIGINAL_APK_SHA256 below, or the build stops.
  --android-libs   a directory holding 32-bit ARM Android libc.so, libdl.so and liblog.so,
                   used only as link inputs (from the same device's /system/lib, or the
                   NDK sysroot stubs for arm-linux-androideabi API 21).

The build compiles a 9 KB shim with clang/lld, renames the package to
com.google.android.youtube.tx so it installs beside the original, keeps the original
Cobalt engine bytes as libcobalt.so, signs with your own key, and refuses to finish if
any entry other than the three expected ones changed.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORIGINAL_APK_SHA256 = '0cb978cccf1f4d1da60d5957a0f5891a10972395d31c69e7420d49ffb5ac0232'
ENGINE_SHA256 = '3fcf3a894628bbe7476e0cf8e7aa3f28d3000766273d4b53e501c4488f2ebfca'
ENGINE_ENTRY = 'lib/armeabi-v7a/libcoat.so'
OLD, NEW = 'com.google.android.youtube.tv', 'com.google.android.youtube.tx'
SIGNATURE_ENTRIES = {'META-INF/CERT.RSA', 'META-INF/CERT.SF', 'META-INF/MANIFEST.MF'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args, **kwargs):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout + result.stderr


def build_tools():
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or Path.home() / 'Android/Sdk')
    tools = sdk / 'build-tools' / os.environ.get('ANDROID_BUILD_TOOLS', '36.0.0')
    for name in ('zipalign', 'apksigner', 'aapt2'):
        if not (tools / name).exists():
            raise SystemExit(f'Missing {tools / name}; set ANDROID_HOME or ANDROID_BUILD_TOOLS.')
    return tools


def compile_shim(build, android_libs, engine, diagnostic):
    link = build / 'link'
    if link.exists():
        shutil.rmtree(link)
    link.mkdir(parents=True)
    for name in ('libc.so', 'libdl.so', 'liblog.so'):
        if not (android_libs / name).is_file():
            raise SystemExit(f'{android_libs / name} is missing')
        shutil.copyfile(android_libs / name, link / name)
    (link / 'libcobalt.so').write_bytes(engine)
    args = ['clang', '--target=armv7a-linux-androideabi21', '-marm', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Oz',
            '-fPIC', '-fvisibility=hidden', '-fstack-protector-strong', '-nostdlib', '-shared', '-fuse-ld=lld',
            '-Wl,-soname,libcoat.so', '-Wl,-z,relro,-z,now,-z,noexecstack', '-Wl,--no-undefined',
            ROOT / 'loader.c', ROOT / 'ad_patch.c', ROOT / 'slots.c', '-L' + str(link), '-Wl,--no-as-needed',
            '-l:libcobalt.so', '-l:libc.so', '-l:libdl.so', '-l:liblog.so', '-o', build / 'libcoat.so']
    if diagnostic:
        args.insert(1, '-DGUARD_DIAGNOSTIC')
    run(args)
    (build / 'shim-elf.txt').write_text(run(['readelf', '-h', '-d', '-Ws', build / 'libcoat.so']))
    return (build / 'libcoat.so').read_bytes()


def signing_material(args):
    if args.keystore:
        if not args.ks_pass_file:
            raise SystemExit('--keystore requires --ks-pass-file')
        return args.keystore, args.ks_pass_file
    private = ROOT / 'private'
    private.mkdir(mode=0o700, exist_ok=True)
    password, key = private / 'password', private / 'research.p12'
    if not key.exists():
        password.write_text(secrets.token_urlsafe(40))
        password.chmod(0o600)
        env = os.environ.copy()
        env['AD_GUARD_KEY_PASSWORD'] = password.read_text()
        run(['keytool', '-genkeypair', '-alias', args.key_alias, '-keystore', key, '-storetype', 'PKCS12',
             '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650', '-dname', 'CN=Video ad guard research build',
             '-storepass:env', 'AD_GUARD_KEY_PASSWORD'], env=env)
        key.chmod(0o600)
        print('Created a research signing key in private/. Keep it to update the installed copy.', file=sys.stderr)
    return key, password


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--original-apk', type=Path, required=True)
    parser.add_argument('--android-libs', type=Path, required=True)
    parser.add_argument('--keystore', type=Path)
    parser.add_argument('--ks-pass-file', type=Path)
    parser.add_argument('--key-alias', default='video-ad-guard')
    parser.add_argument('--diagnostic', action='store_true',
                        help='investigation build: logs large copies and saves one candidate player source to the app cache')
    args = parser.parse_args()

    tools = build_tools()
    original = args.original_apk.read_bytes()
    if digest(original) != ORIGINAL_APK_SHA256:
        raise SystemExit('Original APK digest mismatch: this guard is pinned to one exact YouTube TV build.')
    with zipfile.ZipFile(args.original_apk) as z:
        engine = z.read(ENGINE_ENTRY)
    if digest(engine) != ENGINE_SHA256:
        raise SystemExit('Original Cobalt engine digest mismatch')

    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    shim = compile_shim(build, args.android_libs, engine, args.diagnostic)

    changes = []
    with zipfile.ZipFile(args.original_apk) as source, zipfile.ZipFile(build / 'unsigned.apk', 'w') as dest:
        for info in source.infolist():
            if info.filename in SIGNATURE_ENTRIES:
                continue
            data = source.read(info.filename)
            if info.filename in ('AndroidManifest.xml', 'resources.arsc'):
                before = data
                for encoding in ('utf-8', 'utf-16le'):
                    data = data.replace(OLD.encode(encoding), NEW.encode(encoding))
                if len(before) != len(data):
                    raise SystemExit('Package rename changed a binary size')
                changes.append({'entry': info.filename, 'before_sha256': digest(before), 'after_sha256': digest(data)})
            elif info.filename == ENGINE_ENTRY:
                data = shim
                info.compress_type = zipfile.ZIP_STORED
                changes.append({'entry': info.filename, 'before_sha256': ENGINE_SHA256, 'after_sha256': digest(data)})
            dest.writestr(info, data)
        # Reuse the original engine entry's metadata so repeated builds are byte-identical.
        added = zipfile.ZipInfo('lib/armeabi-v7a/libcobalt.so', date_time=source.getinfo(ENGINE_ENTRY).date_time)
        added.external_attr = source.getinfo(ENGINE_ENTRY).external_attr
        dest.writestr(added, engine, compress_type=zipfile.ZIP_STORED)

    run([tools / 'zipalign', '-f', '-p', '4', build / 'unsigned.apk', build / 'aligned.apk'])
    key, password = signing_material(args)
    apk = build / 'youtube-tv-video-ad-guard-research.apk'
    run([tools / 'apksigner', 'sign', '--ks', key, '--ks-key-alias', args.key_alias,
         '--ks-pass', 'file:' + str(password), '--out', apk, build / 'aligned.apk'])
    (build / 'apk-verification.txt').write_text(run([tools / 'apksigner', 'verify', '--verbose', '--print-certs', apk]))
    run([tools / 'zipalign', '-c', '-p', '4', apk])
    if "package: name='" + NEW + "'" not in run([tools / 'aapt2', 'dump', 'badging', apk]):
        raise SystemExit('Research package identity mismatch')

    with zipfile.ZipFile(args.original_apk) as source, zipfile.ZipFile(apk) as candidate:
        allowed = {c['entry'] for c in changes}
        unchanged = 0
        for name in source.namelist():
            if name.startswith('META-INF/') or name in allowed:
                continue
            if source.read(name) != candidate.read(name):
                raise SystemExit('Unexpected APK change: ' + name)
            unchanged += 1
        if candidate.read('lib/armeabi-v7a/libcobalt.so') != engine:
            raise SystemExit('Original engine changed')

    manifest = {
        'apk': apk.name, 'sha256': digest(apk.read_bytes()), 'package': NEW,
        'original_apk_sha256': ORIGINAL_APK_SHA256, 'original_engine_sha256': ENGINE_SHA256,
        'shim_bytes': len(shim), 'shim_sha256': digest(shim), 'changes': changes, 'unchanged_entries': unchanged,
        'source_pin': json.loads((ROOT / 'source-pin.json').read_text())['original_sha256'],
        'diagnostic': args.diagnostic,
        'scope': 'Video-ad loader early return only; separately signed custom package with exact-source pin.',
    }
    (build / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('apk', 'sha256', 'package', 'shim_bytes', 'shim_sha256', 'unchanged_entries', 'diagnostic')}, indent=2))


if __name__ == '__main__':
    main()
