#!/usr/bin/env python3
"""Build a private native track-one arp on exact stock Digitakt II OS1.16."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.project import doctor,settings,require,git,sha256,source_hashes,write_json
config=settings()
if Path(sys.executable).resolve()!=config['python'].resolve():os.execv(str(config['python']),[str(config['python']),__file__,*sys.argv[1:]])
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--elekloader-reference',type=Path,required=True);p.add_argument('--diagnostics',action='store_true');p.add_argument('--tempo-ui',action='store_true');args=p.parse_args();provenance=doctor()
out=args.output.resolve();require(out.is_relative_to(ROOT/'out/runs'),'Fresh ignored run required');out.mkdir(exist_ok=False);os.environ['DT2_LAB_RUN_DIR']=str(out.relative_to(ROOT/'out/runs'))
from lab.runtime import STOCK_MAIN,STOCK_BLOB,PROFILE
from lab.arp_firmware import patch_cpu
from lab.upload import REFERENCE_REVISION,assemble_container,verify_candidate,digest
reference=args.elekloader_reference.resolve();require(git(reference,'rev-parse','HEAD')==REFERENCE_REVISION,'Unknown codec');require(not git(reference,'status','--porcelain'),'Dirty codec');sys.path.insert(0,str(reference))
from elekloader import syx
from elekloader.codec.aplib import pack_section
report=dict(status='building',firmware='Digitakt II OS1.16',hardware_ready=False,hardware_uploaded=False,source_hashes=provenance['source_hashes'],dependencies=provenance['dependencies'],included=['Native track 1 OFF/UP/ORDER/RANDOM','Keyboard settings encoder G','102 BPM sixteenths, half gate, no latch','Stock live note recording and native AR16 project mode journal'],gaps=['Physical device, physical timing and listening remain unverified','Only track 1 and fixed 102 BPM; tempo edits and MIDI input not supported','Broader view transitions, pattern copy/undo/export and companion cleanup not validated'])
report['diagnostics']=args.diagnostics;report['tempo_ui']=args.tempo_ui
if args.tempo_ui:
 report['included']=['Native track 1 OFF/UP/ORDER/RANDOM','G uses original stock enum sensitivity; push switches mode/rate focus','Stock tempo getter, fractional BPM, 1/4, 1/8, 1/16, 1/32; half gate','Native AR16 v2 project mode/rate journal; v1 import at 1/16','Stock live note recording']
 report['gaps']=['Physical timing and listening of this candidate remain unverified','Track 1 only, no latch or MIDI input; external sync and swing not validated','Pattern copy/undo/export and companion cleanup not validated']
if args.diagnostics:report['included'].append('D1 native readouts: held, PLAY, clock progress, API entries and generated note calls')
try:
 stock=STOCK_MAIN.read_bytes();image,meta=patch_cpu(stock,diagnostics=args.diagnostics,tempo_ui=args.tempo_ui);require(patch_cpu(stock,diagnostics=args.diagnostics,tempo_ui=args.tempo_ui)[0]==image,'Native build differs on repeat');(out/'ARP_MAIN_OS.bin').write_bytes(image);write_json(out/'native-patches.json',meta)
 inputs=json.loads((ROOT/'.local/cpu-inputs.json').read_text());original=Path(inputs['syx']);require(sha256(original)==PROFILE['stock_syx_sha256'],'Unknown stock SYX');container=syx.Syx(original.read_bytes());require(container.section(3)==stock and container.section(7)==STOCK_BLOB.read_bytes(),'Stock fixture mismatch');require(assemble_container(container,{})==container.raw,'Stock reconstruction')
 packed={3:pack_section(image)};raw=assemble_container(container,packed);facts=verify_candidate(raw,container,{3:image});require(raw==assemble_container(container,packed),'Container repeat differs');require(source_hashes()==provenance['source_hashes'],'Source drift')
 name='EXPERIMENTAL_ARP_STOCK_OS1.16_TEMPO_RATE_R2.syx' if args.tempo_ui else 'EXPERIMENTAL_ARP_STOCK_OS1.16_DIAG_D1.syx' if args.diagnostics else 'EXPERIMENTAL_ARP_STOCK_OS1.16.syx';(out/name).write_bytes(raw);report.update(status='target-build-complete',candidate=name,container=facts,cpu={'path':'ARP_MAIN_OS.bin','sha256':digest(image),'native':meta},repeat_exact=True,stock_dsp_unchanged=True,codec_revision=REFERENCE_REVISION)
 print(out/name,flush=True)
except BaseException as e:report.update(status='failed',error=f'{type(e).__name__}: {e}');raise
finally:write_json(out/'manifest.json',report)
