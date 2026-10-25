#!/usr/bin/env python3
"""Bounded native CPU startup from a newly built stock-only arp package."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.project import doctor,settings,require,sha256,write_json
config=settings()
if Path(sys.executable).resolve()!=config['python'].resolve():os.execv(str(config['python']),[str(config['python']),__file__,*sys.argv[1:]])
p=argparse.ArgumentParser(description=__doc__);p.add_argument('package_run',type=Path);p.add_argument('output',type=Path);args=p.parse_args();doctor();package=args.package_run.resolve();out=args.output.resolve();require(out.is_relative_to(ROOT/'out/runs'),'Fresh ignored run required');out.mkdir(exist_ok=False);os.environ['DT2_LAB_RUN_DIR']=str(out.relative_to(ROOT/'out/runs'))
from lab.runtime import REPO
from emu import checkpoint,snapshot
m=json.loads((package/'manifest.json').read_text());require(m['status']=='target-build-complete','Build incomplete');candidate=package/m['candidate'];require(sha256(candidate)==m['container']['sha256'],'Package changed');image=package/'ARP_MAIN_OS.bin';require(sha256(image)==m['cpu']['sha256'],'MAIN changed')
report={'status':'running','hardware':False,'scope':'Native CPU startup with normal emulator boot peer; stock DSP unchanged, no coupled/hardware claim','candidate_sha256':sha256(candidate)}
try:
 os.chdir(REPO);saved=checkpoint.make([400_000_000],prefix=str(out/'boot'),syx=str(candidate),img_path=str(image));require(len(saved)==1,'Bounded startup checkpoint missing');machine,extra,_=snapshot.restore(str(out/'boot400M.snap'))
 for w in m['cpu']['native']['writes']:
  if w['label'] in ('pointer','binding'):continue
  expected=bytes.fromhex(w['after']);require(bytes(machine.uc.mem_read(w['address'],len(expected)))==expected,'Startup changed '+w['label'])
 ptr=m['cpu']['native']['locations']['pointer'];state=int.from_bytes(machine.uc.mem_read(ptr,4),'big');report.update(status='passed',state_address=state,checkpoint='boot400M.snap',static_patch_writes_preserved=True)
except BaseException as e:report.update(status='failed',error=f'{type(e).__name__}: {e}');raise
finally:write_json(out/'boot.json',report)
