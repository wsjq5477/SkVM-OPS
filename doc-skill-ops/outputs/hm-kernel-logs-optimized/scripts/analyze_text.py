#!/usr/bin/env python3
import argparse, json, re, time
from pathlib import Path

SECTIONS=['故障摘要','关键日志','时间线','根因分析','建议排查方向']

def analyze(path):
    start=time.perf_counter()
    text=Path(path).read_text(encoding='utf-8', errors='replace')
    lines=text.splitlines()
    regs=re.search(r'ESR=([0-9a-fA-F]+).*?FAR=([0-9a-fA-F]+).*?ELR=([0-9a-fA-F]+)', text, re.S)
    thr=re.search(r'name=([^,]+),\s*tid=(\d+),\s*state=([^,]+).*?cpu=(\d+).*?cur_rq=(\d+).*?cur_prio=(\d+)', text, re.S)
    stack=[l for l in lines if '<' in l and '>' in l]
    key=[l for l in lines if 'PANIC' in l or 'ESR=' in l or 'Stack backtrace' in l][:8]
    esr=regs.group(1) if regs else ''
    ec=f'0x{((int(esr,16)>>26)&0x3f):x}' if esr else ''
    return {'summary':{'fault_type':'KERNEL_UNIMPLEMENTED_EXCEPTION' if 'Exception Dump Start' in text else 'UNKNOWN','crash_thread':thr.group(1) if thr else 'unknown','crash_cpu':thr.group(4) if thr else 'unknown'},'registers':{'esr':esr,'far':regs.group(2) if regs else '', 'elr':regs.group(3) if regs else ''},'esr':{'ec':ec,'fault_type':'BRK instruction' if ec=='0x3c' else 'unknown'},'key_logs':key,'timeline':[{'time':'','raw_log':l,'description':'relevant'} for l in key[:5]],'call_stack':stack,'required_sections':SECTIONS,'metrics':{'elapsed_ms':round((time.perf_counter()-start)*1000,3)}}

def main():
    p=argparse.ArgumentParser(); p.add_argument('log_path'); p.add_argument('--handoff', action='store_true'); p.add_argument('--pretty', action='store_true'); a=p.parse_args(); print(json.dumps(analyze(a.log_path), ensure_ascii=False, indent=2 if a.pretty else None))
if __name__=='__main__': main()
