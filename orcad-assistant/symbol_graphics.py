"""Save and independently read back line-based symbols using Capture's native API."""
import math
from pathlib import Path

def apply_and_verify(olb,project,env,log):
    import assistant_core as c,build_pipeline as b
    graphic=project['symbol_graphics'];segments=graphic['segments'];designator=graphic.get('designator','U')
    if designator not in ('R','C','L','D','Q','U'):raise ValueError('符号位号无效')
    if not 1<=len(segments)<=500 or any(len(s)!=4 or any(not isinstance(n,(int,float)) or not math.isfinite(n) or int(n)!=n or abs(n)>30000 for n in s) for s in segments):raise ValueError('符号图形线段无效')
    q=c.generator.tcl_quote;olb=Path(olb).resolve();folder=olb.parent
    head=['package require Tcl 8.4',f'load {q(env["dll"])} DboTclWriteBasic','proc str {s} {return [DboTclHelper_sMakeCString $s]}','proc pt {x y} {return [DboTclHelper_sMakeCPoint $x $y]}','set st [DboState]','set session [DboTclHelper_sCreateSession]',f'set lib [$session GetLib [str {q(olb.as_posix())}] $st]','if {$lib eq "NULL" || [$st Failed]} {error "Library open failed"}','set parts [$lib NewPartsIter $st]; set part [$parts NextPart $st]','if {$part eq "NULL" || [$st Failed]} {error "Part missing"}','set name [str ""]; $part GetName $name',f'if {{[DboTclHelper_sGetConstCharPtr $name] ne {q(project["device"]+".Normal")}}} {{error "Part identity mismatch"}}']
    lines=head+['set it [$part NewVectorsIter $st $IterDefs_ALL]','set remove {}','for {set j 0} {$j<1000} {incr j} {set vs [DboState];set v [$it NextVector $vs];if {[$vs Failed] || $v eq "NULL"} break;lappend remove $v}','if {$j==1000} {error "Vector limit"}','delete_DboGraphicObjectVectorsIter $it','foreach v $remove {$part DeleteVector $v}']
    for x,y,a,z in segments:lines.append(f'if {{[$part NewLine $st [pt {int(x)} {int(y)}] [pt {int(a)} {int(z)}]] eq "NULL"}} {{error "NewLine failed"}}')
    for text in graphic.get('texts',[]):
        label=str(text['text']);x=int(text['x']);y=int(text['y']);height=int(text['height']);half=round(len(label)*height*.3)
        if not label.isalnum() or len(label)>12 or height<6 or height>30:raise ValueError('符号封装文字无效')
        left=x-half;top=y-height//2
        lines += [f'set font [DboTclHelper_sMakeLOGFONT "Arial" {height} 0 0 0 400 0 0 0 1 0 0 0 0]',f'set bound [DboTclHelper_sMakeCRect {left} {top} {x+half} {y+(height+1)//2}]',f'if {{[$part NewCommentText $st [str {q(label)}] $bound [pt {left} {top}] $font] eq "NULL"}} {{error "Comment text failed"}}']
    if 'pin_names_visible' in graphic:lines.append('$part SetPinNamesAreVisible '+str(int(graphic['pin_names_visible'])))
    if graphic.get('pin_length_style')=='short':
        lines+=['set pins [$part NewPinsIter $st]','for {set n 0} {$n<1000} {incr n} {set ps [DboState];set pin [$pins NextPin $ps];if {[$ps Failed] || $pin eq "NULL"} break;$pin SetIsLong 0}']
    lines+=['set pkg [$part GetPackagePtr]',f'$pkg SetDesignator [str {q(designator)}]',f'$pkg SetReferenceTemplate [str {q(designator)}]',f'$part SetReference [str {q(designator)}]','$lib SavePart $part','$lib SavePackage $pkg','$session MarkAllLibForSave $lib','$session SaveLib $lib','DboTclHelper_sDeleteSession $session','puts "GRAPHICS_COMPLETE"']
    script=folder/'graphics.tcl';script.write_text('\n'.join(lines),encoding='utf8')
    if 'GRAPHICS_COMPLETE' not in b.run_tcl(script,folder,env,log):raise ValueError('符号图形保存未完成')
    lines=head+['set it [$part NewVectorsIter $st $IterDefs_ALL]','for {set j 0} {$j<1000} {incr j} {set vs [DboState];set v [$it NextVector $vs];if {[$vs Failed] || $v eq "NULL"} break;if {[$v GetObjectType] == $DboBaseObject_COMMENT_TEXT} {set tx [DboVectorToDboCommentText $v];set label [str ""]; $tx GetText $label;set loc [$tx GetLocation $st];puts "TEXT|[DboTclHelper_sGetConstCharPtr $label]|[DboTclHelper_sGetCPointX $loc]|[DboTclHelper_sGetCPointY $loc]";continue};set line [DboVectorToDboLine $v];set a [$line GetStart $st];set z [$line GetEnd $st];puts "LINE|[DboTclHelper_sGetCPointX $a]|[DboTclHelper_sGetCPointY $a]|[DboTclHelper_sGetCPointX $z]|[DboTclHelper_sGetCPointY $z]"}','if {$j==1000} {error "Vector limit"}','puts "NAMES_VISIBLE|[$part GetPinNamesAreVisible $st]"','set pins [$part NewPinsIter $st]','for {set n 0} {$n<1000} {incr n} {set ps [DboState];set pin [$pins NextPin $ps];if {[$ps Failed] || $pin eq "NULL"} break;puts "PIN_LONG|[$pin GetIsLong $st]"}','DboTclHelper_sDeleteSession $session','puts "GRAPHICS_VERIFIED"']
    script=folder/'graphics-readback.tcl';script.write_text('\n'.join(lines),encoding='utf8');output=b.run_tcl(script,folder,env,log)
    actual=[list(map(int,line.split('|')[1:])) for line in output.splitlines() if line.startswith('LINE|')]
    if 'GRAPHICS_VERIFIED' not in output or sorted(actual)!=sorted(segments):raise ValueError('OLB图形逐线回读不一致')
    actual_texts=[line.split('|')[1:] for line in output.splitlines() if line.startswith('TEXT|')]
    wanted=[[str(t['text']),str(int(t['x'])-round(len(str(t['text']))*int(t['height'])*.3)),str(int(t['y'])-int(t['height'])//2)] for t in graphic.get('texts',[])]
    if sorted(actual_texts)!=sorted(wanted):raise ValueError('原生封装文字回读不一致')
    if 'pin_names_visible' in graphic and f'NAMES_VISIBLE|{int(graphic["pin_names_visible"])}' not in output:raise ValueError('原生PIN NAME显示设置未保存')
    if graphic.get('pin_length_style')=='short':
        long_flags=[line for line in output.splitlines() if line.startswith('PIN_LONG|')]
        if len(long_flags)!=len(project['pins']) or any(line!='PIN_LONG|0' for line in long_flags):raise ValueError('原生引脚没有保存为Short')
    return dict(texts=actual_texts,pin_names_visible=graphic.get('pin_names_visible',True),pin_style=graphic.get('pin_length_style','default'),segments=len(actual),designator=designator,frame_visible=False,status='PASS')
