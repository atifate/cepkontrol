"""Deployment helper. Reads the SSH password from stdin; never saves it."""
import pathlib
import sys
import getpass
import os
import paramiko

client = paramiko.SSHClient()
client.load_system_host_keys()
known = pathlib.Path.home() / '.ssh' / 'known_hosts'
if known.exists():
    client.load_host_keys(str(known))
password = getpass.getpass('SSH password: ')
target = os.environ.get('ACIKDESTEK_SSH_HOST', '192.168.1.69')
if target not in ('192.168.1.69', '100.77.178.100'):
    raise ValueError('Unknown server address')
if target == '100.77.178.100' and not client.get_host_keys().lookup(target):
    # Both addresses belong to the same server. Verify its already trusted
    # LAN host key over the overlay too; never accept an unknown host key.
    trusted = client.get_host_keys().lookup('192.168.1.69')
    if not trusted:
        raise ValueError('Previously verified server key is missing')
    for kind, key in trusted.items():
        client.get_host_keys().add(target, kind, key)
client.connect(target, username='ati', password=password,
               look_for_keys=False, allow_agent=False, timeout=10)


def run(command, sudo=False):
    stdin, stdout, stderr = client.exec_command(command, timeout=180)
    if sudo:
        stdin.write(password + '\n')
        stdin.flush()
    stdin.channel.shutdown_write()
    output = stdout.read().decode(errors='replace')
    errors = stderr.read().decode(errors='replace')
    print(output, end='', flush=True)
    if errors:
        print(errors, end='', file=sys.stderr, flush=True)
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f'Remote command failed ({status})')


try:
    if len(sys.argv) == 1 or sys.argv[1] == 'probe':
        run('uname -a; python3 --version; command -v docker || true; '
            'test -d /home/ati/acikdestek && ls -la /home/ati/acikdestek || true; '
            'ss -ltn | head -12')
    elif sys.argv[1] == 'deploy':
        run('mkdir -p /home/ati/acikdestek')
        sftp = client.open_sftp()
        sftp.put('relay.py', '/home/ati/acikdestek/relay.py')
        sftp.put('server/acikdestek.service', '/home/ati/acikdestek/acikdestek.service')
        sftp.close()
        run('python3 -m venv /home/ati/acikdestek/venv')
        run('/home/ati/acikdestek/venv/bin/pip install websockets==17.2')
        run('sudo -S -p "" install -m 644 /home/ati/acikdestek/acikdestek.service '
            '/etc/systemd/system/acikdestek.service', sudo=True)
        run('sudo -S -p "" systemctl daemon-reload', sudo=True)
        run('sudo -S -p "" systemctl enable --now acikdestek.service', sudo=True)
        run('systemctl --no-pager status acikdestek.service')
    elif sys.argv[1] == 'venv':
        run('sudo -S -p "" apt-get update -qq', sudo=True)
        run('sudo -S -p "" apt-get install -y python3-venv', sudo=True)
    elif sys.argv[1] == 'status':
        run('systemctl --no-pager status acikdestek.service; '
            'journalctl -u acikdestek.service -n 10 --no-pager')
    elif sys.argv[1] == 'diagnose':
        run('date -Is; uptime; free -m; '
            'systemctl show acikdestek tailscaled -p ActiveState -p NRestarts -p ActiveEnterTimestamp; '
            'tailscale funnel status; '
            'journalctl -u acikdestek.service --since "24 hours ago" -n 80 --no-pager; '
            'journalctl -u tailscaled --since "24 hours ago" -n 120 --no-pager '
            '| sed -E "s#https://[^ ]+#<url>#g"; '
            'ss -s')
        run('sudo -S -p "" journalctl -u acikdestek.service -u tailscaled '
            '--since "2 hours ago" -n 160 --no-pager '
            '| sed -E "s#https://[^ ]+#<url>#g"', sudo=True)
    elif sys.argv[1] == 'network':
        run('ip -4 -brief address; command -v tailscale >/dev/null && tailscale status || true; '
            'command -v ufw >/dev/null && sudo -n ufw status || true')
    elif sys.argv[1] == 'relay-logs':
        run('sudo -S -p "" journalctl -u acikdestek.service --since "15 minutes ago" --grep "acikdestek.relay" -n 80 --no-pager', sudo=True)
    elif sys.argv[1] == 'tailscale-install':
        sftp = client.open_sftp()
        sftp.put('build-tools/tailscale-install.sh', '/home/ati/acikdestek/tailscale-install.sh')
        sftp.close()
        run('sudo -S -p "" sh /home/ati/acikdestek/tailscale-install.sh', sudo=True)
        run('sudo -S -p "" tailscale up --hostname=acikdestek-sunucu --accept-dns=false --timeout=10s || true', sudo=True)
    elif sys.argv[1] == 'tailscale-status':
        run('tailscale status; tailscale ip -4')
    elif sys.argv[1] == 'funnel':
        run('sudo -S -p "" tailscale funnel --bg 8765', sudo=True)
    elif sys.argv[1] == 'funnel-status':
        run('tailscale funnel status; systemctl is-active acikdestek tailscaled')
    elif sys.argv[1] == 'mobile-deploy':
        run('test -f /home/ati/acikdestek/relay.py.pre-mobile || cp /home/ati/acikdestek/relay.py /home/ati/acikdestek/relay.py.pre-mobile; mkdir -p /home/ati/acikdestek/mobile')
        sftp = client.open_sftp()
        sftp.put('relay.py', '/home/ati/acikdestek/relay.py')
        for name in ('index.html', 'mobile.js', 'mobile.css', 'manifest.webmanifest', 'sw.js', 'icon-180.png', 'icon-192.png', 'icon-512.png'):
            sftp.put('mobile/' + name, '/home/ati/acikdestek/mobile/' + name)
        sftp.close()
        run('sudo -S -p "" systemctl restart acikdestek.service', sudo=True)
        run('systemctl is-active acikdestek.service')
    elif sys.argv[1] == 'mobile-assets':
        sftp = client.open_sftp()
        for name in ('index.html', 'mobile.js', 'mobile.css', 'manifest.webmanifest', 'sw.js', 'icon-180.png', 'icon-192.png', 'icon-512.png'):
            sftp.put('mobile/' + name, '/home/ati/acikdestek/mobile/' + name)
        sftp.close()
        print('Mobile assets updated.')
finally:
    client.close()
