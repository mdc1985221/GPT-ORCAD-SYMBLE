"""Conservative cross-version project convention, not an exhaustive Cadence parser."""
import re
RESERVED={'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(1,10)),*('LPT'+str(i) for i in range(1,10))}
def validate(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,30}',name) or name in RESERVED:
        raise ValueError('封装库名使用大写字母、数字、下划线，字母开头，最多31字符，不能使用Windows保留名')
    return name
def mm(value):return format(float(value),'.6f').rstrip('0').rstrip('.').replace('.','P')
def package(part,family,width,height,pitch=None):
    stem=re.sub('[^A-Z0-9]+','_',part.upper()).strip('_')
    if pitch is not None and (pitch<=0 or abs(pitch*1000-round(pitch*1000))>1e-6):raise ValueError('脚距须为正毫米值，并可精确表示为整数微米')
    name=f'{stem}_{family.upper()}_{mm(width)}X{mm(height)}'+(f'_P{round(pitch*1000):04d}' if pitch is not None else '')
    return validate(name)
