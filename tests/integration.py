#!/usr/bin/env python3
"""Run isolated end-to-end wheel tests in a nested Hyprland session.

Requires a running Wayland desktop plus Hyprland, foot, wev, wtype, a C
compiler, wayland-scanner, pkg-config, and wayland-client development files.
The nested compositor opens a temporary window; the parent workspace is not
used as a test target. Run from the repository root: python3 tests/integration.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
for tool in ('Hyprland', 'hyprctl', 'foot', 'wev', 'wtype', 'wayland-scanner', 'pkg-config', 'cc', 'stdbuf'):
    if not shutil.which(tool):
        raise SystemExit(f'Missing test dependency: {tool}')
if not os.environ.get('WAYLAND_DISPLAY'):
    raise SystemExit('A parent Wayland session is required for nested Hyprland')
subprocess.run(['make', 'all'], cwd=ROOT, check=True)
plugin = ROOT / 'thumbwheel.so'
children = []

def eventually(predicate, description, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError(f'Timed out: {description}')

with tempfile.TemporaryDirectory(prefix='thumbwheel-integration-') as temp:
    temp = Path(temp)
    xml = ROOT / 'tests/wlr-virtual-pointer-unstable-v1.xml'
    subprocess.run(['wayland-scanner','client-header',str(xml),str(temp/'virtual-pointer.h')],check=True)
    subprocess.run(['wayland-scanner','private-code',str(xml),str(temp/'protocol.c')],check=True)
    flags = subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True).split()
    subprocess.run(['cc','-Wall','-Wextra',str(ROOT/'tests/wheel.c'),str(temp/'protocol.c'),'-I',str(temp),'-o',str(temp/'wheel'),*flags],check=True)
    config = temp/'hyprland.lua'
    config.write_text('hl.config({ general = { layout = "dwindle" }, animations = { enabled = false } })\n')
    parent_env = os.environ.copy()
    parent_env.update({'HYPRLAND_NO_CRASHREPORTER':'1','HYPRLAND_NO_RT':'1','LIBGL_ALWAYS_SOFTWARE':'1'})
    with (temp/'hyprland.log').open('w') as log:
        compositor = subprocess.Popen(['Hyprland','--config',str(config)],env=parent_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            def get_instance():
                if compositor.poll() is not None:
                    raise RuntimeError(f'Nested compositor exited: {(temp/"hyprland.log").read_text()[-3000:]}')
                instances = json.loads(subprocess.check_output(['hyprctl','instances','-j'],env=parent_env,stderr=subprocess.DEVNULL))
                return next((x for x in instances if x['pid']==compositor.pid),None)
            instance=eventually(get_instance,'nested compositor')
            h=['hyprctl','--instance',instance['instance']]
            client_env=parent_env | {'WAYLAND_DISPLAY':instance['wl_socket'],'HYPRLAND_INSTANCE_SIGNATURE':instance['instance']}
            def hypr(*args):
                return subprocess.check_output(h+list(args),env=parent_env,text=True).strip()
            def clients(): return json.loads(hypr('clients','-j'))
            def workspace_windows(workspace):
                return [w for w in clients() if w['workspace']['id']==workspace]
            def positions(workspace):
                return {w['address']:w['at'][0] for w in workspace_windows(workspace)}
            def differences(a,b): return {b[k]-value for k,value in a.items() if k in b}
            def start_wev(name):
                output=(temp/f'{name}.log').open('w')
                proc=subprocess.Popen(['stdbuf','-oL','wev'],env=client_env,stdout=output,stderr=subprocess.DEVNULL)
                children.append((proc,output))
                return temp/f'{name}.log'
            def axis_count(path): return path.read_text().count('axis: 1 (horizontal)')
            def wheel(direction,count=1,delta=15,axis='horizontal'):
                subprocess.run([str(temp/'wheel'),str(direction),str(count),str(delta),axis],env=client_env,check=True,timeout=5)
                time.sleep(.3)
            def warp(window):
                x,y=window['at']; width,height=window['size']
                hypr('dispatch',f'hl.dsp.cursor.move({{ x = {x+width//2}, y = {y+height//2} }})')
                time.sleep(.2)
            def pass_wheel(path):
                before=axis_count(path);wheel(1)
                assert axis_count(path)>before, f'horizontal event was not passed to client: {path.read_text()[-2000:]}'

            assert hypr('plugin','load',str(plugin))=='ok'
            assert 'xiemin-thumbwheel' in hypr('plugin','list')
            first=start_wev('dwindle')
            win=eventually(lambda: next((w for w in workspace_windows(1) if w['class']=='wev'),None),'dwindle wev')
            warp(win);pass_wheel(first)
            print('PASS: horizontal wheel passes through on dwindle layout',flush=True)

            hypr('eval','hl.workspace_rule({ workspace = "2", layout = "scrolling" })')
            hypr('dispatch','hl.dsp.focus({ workspace = "2" })')
            for i in range(3):
                proc=subprocess.Popen(['foot','--app-id',f'thumbwheel-test-{i}','sh','-c','sleep 180'],env=client_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                children.append((proc,None));time.sleep(.15)
            second=start_wev('scrolling')
            eventually(lambda:len(workspace_windows(2))==4,'scrolling windows')
            win=next(w for w in workspace_windows(2) if w['class']=='wev')
            hypr('dispatch',f'hl.dsp.focus({{ window = "address:{win["address"]}" }})');time.sleep(.35)
            warp(next(w for w in workspace_windows(2) if w['class']=='wev'))
            time.sleep(.35);a=positions(2); log_before=axis_count(second)
            direction = 1 if min(a.values()) < -250 else -1
            wheel(direction,3,15);b=positions(2);wheel(-direction,3,15);c=positions(2)
            assert differences(a,b)=={direction*240} and differences(a,c)=={0},(direction,a,b,c,differences(a,b),differences(a,c),hypr('plugin','list'),hypr('activeworkspace','-j'),second.read_text()[-1200:])
            assert axis_count(second)==log_before, 'normal wheel leaked to client on scrolling layout'
            a=positions(2);wheel(direction,1,7.5);b=positions(2);wheel(-direction,1,7.5);c=positions(2)
            assert differences(a,b)=={direction*40} and differences(a,c)=={0},(differences(a,b),differences(a,c))
            print('PASS: scrolling uses proportional input and consumes normal wheel events',flush=True)

            warp(next(w for w in workspace_windows(2) if w['class']=='wev'))
            mod=subprocess.Popen(['wtype','-M','shift','-s','1400','-m','shift'],env=client_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            children.append((mod,None));time.sleep(.35);a=positions(2);pass_wheel(second);b=positions(2);mod.wait(timeout=3)
            assert differences(a,b)=={0},differences(a,b)
            print('PASS: modified wheel passes to client without moving layout',flush=True)

            warp(next(w for w in workspace_windows(2) if w['class']=='wev'))
            before=second.read_text().count('axis: 0 (vertical)');a=positions(2)
            wheel(1,axis='vertical');b=positions(2)
            assert second.read_text().count('axis: 0 (vertical)')>before, 'vertical event was not passed to client'
            assert differences(a,b)=={0},differences(a,b)
            print('PASS: vertical wheel passes to client without moving layout',flush=True)

            # Moving a client to a special workspace makes it available to toggle.
            address=next(w['address'] for w in workspace_windows(2) if w['class']=='wev')
            hypr('dispatch',f'hl.dsp.window.move({{ workspace = "special:wheeltest", window = "address:{address}" }})')
            if not json.loads(hypr('monitors','-j'))[0]['specialWorkspace']['name']:
                hypr('dispatch','hl.dsp.workspace.toggle_special("wheeltest")')
            eventually(lambda: json.loads(hypr('monitors','-j'))[0]['specialWorkspace']['name']=='special:wheeltest', 'special workspace active')
            special=eventually(lambda: next((w for w in clients() if w['address']==address and w['workspace']['name']=='special:wheeltest' and w['visible']),None),'special workspace')
            warp(special);pass_wheel(second)
            print('PASS: horizontal wheel passes through on special workspace',flush=True)
            hypr('dispatch','hl.dsp.workspace.toggle_special("wheeltest")')

            # Unloading while the idle timer is armed must not call freed code.
            subprocess.run([str(temp/'wheel'),'1','1','7.5'],env=client_env,check=True,timeout=5)
            assert hypr('plugin','unload',str(plugin))=='ok'
            time.sleep(.3)
            assert 'xiemin-thumbwheel' not in hypr('plugin','list')
            assert hypr('plugin','load',str(plugin))=='ok'

            # An old idle callback must not focus the workspace we just left.
            subprocess.run([str(temp/'wheel'),'1','1','7.5'],env=client_env,check=True,timeout=5)
            hypr('dispatch','hl.dsp.focus({ workspace = "1" })');time.sleep(.35)
            assert json.loads(hypr('activeworkspace','-j'))['id']==1
            assert hypr('plugin','unload',str(plugin))=='ok'
            assert not hypr('configerrors')
            print('PASS: timer cleanup and workspace switch leave compositor healthy',flush=True)
        finally:
            for proc, output in children:
                if proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
                if output:output.close()
            if compositor.poll() is None:
                compositor.terminate()
                try:compositor.wait(timeout=8)
                except subprocess.TimeoutExpired:compositor.kill();compositor.wait()
