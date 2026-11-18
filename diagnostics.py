"""Bounded rotating diagnostics and an explicit, data-minimal export."""
import json,logging,logging.handlers,os,platform,sys,tempfile,threading,zipfile,re
from pathlib import Path
from PySide6.QtCore import qVersion,qInstallMessageHandler

VERSION='v1.0.1'
def redact(text,root):
    for path,label in ((str(Path(root)),'%APP_DATA%'),(str(Path(root).resolve()),'%APP_DATA%'),(str(Path.home()),'%USERPROFILE%')):
        text=text.replace(path,label).replace(path.replace('\\','/'),label)
    return re.sub(r'(?i)[a-z]:[\\/]+Users[\\/]+[^\\/\s]+','%USERPROFILE%',text)

def install_logging(root):
    root=Path(root);directory=root/'logs';directory.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('ff14');logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):handler.close();logger.removeHandler(handler)
    class Formatter(logging.Formatter):
        def format(self,record):return redact(super().format(record),root)
    handler=logging.handlers.RotatingFileHandler(directory/'app.log',maxBytes=2*1024*1024,backupCount=2,encoding='utf-8')
    handler.setFormatter(Formatter('%(asctime)s %(levelname)s %(message)s'));logger.addHandler(handler)
    sys.excepthook=lambda kind,value,tb:logger.error('Unhandled exception',exc_info=(kind,value,tb))
    threading.excepthook=lambda args:logger.error('Worker exception',exc_info=(args.exc_type,args.exc_value,args.exc_traceback))
    def qt_message(kind,context,message):logger.warning('Qt: %s',message)
    qInstallMessageHandler(qt_message);logger.info('Application started %s; Python %s; Qt %s',VERSION,platform.python_version(),qVersion())
    return logger

def export_diagnostics(root,destination):
    root=Path(root);destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    for handler in logging.getLogger('ff14').handlers:handler.flush()
    fd,name=tempfile.mkstemp(prefix='.diagnostics-',suffix='.zip',dir=destination.parent);os.close(fd)
    try:
        with zipfile.ZipFile(name,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('environment.json',json.dumps({'app':VERSION,'system':platform.system(),'release':platform.release(),'python':platform.python_version(),'qt':qVersion()},ensure_ascii=False,indent=2))
            sources=[*sorted((root/'logs').glob('app.log*')),root/'sr_roulette.log']
            for source in sources:
                if not source.is_file() or not source.resolve().is_relative_to(root.resolve()):continue
                try:
                    with source.open('rb') as stream:
                        stream.seek(max(0,os.fstat(stream.fileno()).st_size-1024*1024))
                        content=stream.read(1024*1024).decode('utf-8',errors='replace')
                except FileNotFoundError:
                    # A rotated log can disappear between listing and opening.
                    continue
                archive.writestr('logs/'+source.name,redact(content,root))
        os.replace(name,destination)
    finally:Path(name).unlink(missing_ok=True)
