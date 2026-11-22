import os, sys, json, re, uuid, subprocess, shutil, base64, threading, zipfile, time, urllib.request, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent; os.chdir(ROOT)
MEDIA=Path(os.getenv('TK_MEDIA_DIR', str(ROOT/'media'))); MEDIA.mkdir(parents=True, exist_ok=True)
MODEL=os.getenv('TK_MODEL','qwen2.5vl:3b'); WHISPER=os.getenv('TK_WHISPER','small'); JOBS={}
PORT=int(os.getenv('PORT','8768'))
ALLOWED_ORIGINS=[x.strip() for x in os.getenv('ALLOWED_ORIGINS','*').split(',') if x.strip()]
MAX_UPLOAD=int(os.getenv('MAX_UPLOAD_BYTES','150000000'))
def run(*args, timeout=600):
 p=subprocess.run(args,capture_output=True,timeout=timeout)
 if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-700:])
 return p.stdout

def local_ai(prompt, images=()):
 payload={'model':MODEL,'stream':False,'format':'json','messages':[{'role':'user','content':prompt,'images':[base64.b64encode(Path(p).read_bytes()).decode() for p in images]}],'options':{'temperature':0.2}}
 req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=240) as r: return json.loads(json.load(r)['message']['content'])
def acquire(link, folder):
 p=urlsplit(link)
 if p.scheme!='https' or p.hostname not in ('www.tiktok.com','tiktok.com','vm.tiktok.com','vt.tiktok.com') or p.username or p.password: raise ValueError('请输入有效 TikTok HTTPS 链接')
 if not importlib.util.find_spec('yt_dlp'): raise RuntimeError('缺少开放网页采集组件，请先执行安装程序')
 # Public, accessible video only; no cookies, login bypass, or proxy tricks.
 raw=run(sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-warnings','--max-filesize','150M','--socket-timeout','25','--retries','1','--extractor-retries','1','--merge-output-format','mp4','-f','bv*[height<=1080]+ba/b[height<=1080]/b','--print-json','--no-simulate','-o',str(folder/'source.%(ext)s'),'--',link,timeout=180)
 meta=json.loads(raw.decode().strip().splitlines()[-1]); paths=[p for p in folder.glob('source.*') if p.suffix.lower() in ('.mp4','.webm','.mkv','.mov')]
 if not paths: raise RuntimeError('未取得可下载视频；请确认权限、网络或使用本地上传')
 return paths[0], {'name':meta.get('title') or 'TikTok 视频','views':meta.get('view_count'),'likes':meta.get('like_count'),'comments':meta.get('comment_count'),'shares':meta.get('repost_count'),'source':'TikTok 公开网页采集（采集时快照）','link':link,'capturedAt':time.strftime('%Y-%m-%d %H:%M:%S')}
def process(path,folder,meta,job,ai=True,asr=True):
 def stage(msg):job['stage']=msg
 stage('正在转换原视频')
 duration=float(run('ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)))
 if not 0<duration<=600: raise ValueError('仅支持10分钟以内的视频')
 original=folder/'original.mp4'; run('ffmpeg','-y','-v','error','-i',str(path),'-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(original))
 stage('正在检测切镜点')
 p=subprocess.run(['ffmpeg','-hide_banner','-i',str(original),'-vf',"select='gt(scene,0.35)',showinfo",'-an','-f','null','-'],capture_output=True,text=True,timeout=300)
 if p.returncode: raise RuntimeError('切镜检测失败')
 cuts=[0.0]
 for t in sorted(set(float(x) for x in re.findall(r'pts_time:([0-9.]+)',p.stderr))):
  if t-cuts[-1]>=0.25 and duration-t>=0.25: cuts.append(t)
 cuts.append(duration)
 if len(cuts)>201: raise ValueError('候选镜头超过200个，请缩短视频后重试')
 transcript=[]; warnings=[]; asr_ok=False
 if asr:
  stage('本地语音识别（首次可能下载模型）')
  try:
   from faster_whisper import WhisperModel
   wm=WhisperModel(WHISPER,device='cpu',compute_type='int8'); segs,_=wm.transcribe(str(original),vad_filter=True); transcript=[{'start':s.start,'end':s.end,'text':s.text.strip()} for s in segs]; asr_ok=True
  except Exception as e: warnings.append('语音识别未完成：'+str(e)[:200])
 rows=[]; frames=[]; clips=[]; analyses=0; ai_error=None; base='/media/'+folder.name+'/'
 for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
  stage(f'生成分镜 {i+1}/{len(cuts)-1}')
  clip=folder/f'shot_{i+1:03}.mp4'; run('ffmpeg','-y','-v','error','-ss',str(a),'-i',str(original),'-t',str(b-a),'-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(clip))
  imgs=[]
  for j,t in enumerate(sorted(set([a+(b-a)*.15,(a+b)/2,a+(b-a)*.85]))):
   jpg=folder/f'frame_{i+1:03}_{j}.jpg'; run('ffmpeg','-y','-v','error','-ss',str(min(t,duration-.01)),'-i',str(original),'-frames:v','1','-vf','scale=480:-2',str(jpg)); imgs.append(jpg); frames.append({'time':t,'image':base+jpg.name})
  speech=' '.join(s['text'] for s in transcript if s['start']<b and s['end']>a)
  row=[f'{a:.2f}–{b:.2f}','未执行画面语义分析',speech or ('未识别到语音' if asr_ok else '语音未分析'),'候选切镜（画面变化检测）','音效未分析','营销目的未分析']
  extra={}
  if ai and not ai_error:
   stage(f'本地AI分析 {i+1}/{len(cuts)-1}')
   try:
    ans=local_ai('你是短视频分析师。仅据三张按时间排序的关键帧和以下语音转录判断，不确定就标未知。不得把推测写成事实，不可推断音效。输出JSON字符串字段 visual（画面人物动作背景及屏幕文字）、translation（中文翻译，仅翻译转录）、camera（景别及可观察运镜）、editing（剪辑及转场）、purpose（推测营销作用）、reshoot（原创复拍建议）。转录：'+json.dumps(speech,ensure_ascii=False),imgs)
    for k in ['visual','translation','camera','editing','purpose','reshoot']: extra[k]=str(ans.get(k,'未知'))
    row[1]=extra['visual']; row[2]+='\n中文：'+extra['translation'] if speech else ''; row[3]=extra['camera']+'；'+extra['editing']; row[5]=extra['purpose']; analyses+=1
   except Exception as e: ai_error=str(e)[:200]; warnings.append('本地AI未完成：'+ai_error)
  rows.append(row); clips.append({'start':a,'end':b,'url':base+clip.name,'frames':[base+p.name for p in imgs],'detail':extra})
 summary={ 'hook': '尚未完成语义分析','structure':f'检测到 {len(rows)} 个候选镜头；非人工确认的真实剪辑边界','strength':'已保存真实片段与关键帧','risk':'播放指标仅为采集快照；无留存或成交数据，不能判定爆款原因。音效未分析。','recommendation':'检查镜头边界、核对字幕及素材使用权。'}
 if analyses==len(rows) and analyses:
  try:
   stage('生成综合诊断'); ans=local_ai('仅依据以下逐镜头分析输出中文JSON，字段hook,structure,strength,risk,recommendation。明确营销结论是推测，不能虚构指标或音效。'+json.dumps(rows,ensure_ascii=False)); summary.update({k:str(ans[k]) for k in summary if k in ans})
  except Exception as e: warnings.append('综合AI诊断未完成：'+str(e)[:150])
 result={**meta,'rows':rows,'frames':frames,'clips':clips,'transcript':transcript,'summary':summary,'duration':duration,'videoUrl':base+'original.mp4','originalUrl':base+'original.mp4','reportUrl':base+'report.xlsx','zipUrl':base+'export.zip','note':f'已生成 {len(rows)} 个独立 MP4；语音：'+('完成' if asr_ok else '未完成/未启用')+f'；AI分镜 {analyses}/{len(rows)}。'+'；'.join(warnings),'aiCount':analyses,'asrOk':asr_ok,'warnings':warnings}
 stage('生成Excel及ZIP')
 from openpyxl import Workbook
 from openpyxl.styles import Font, PatternFill, Alignment
 w=Workbook(); ws=w.active;ws.title='逐镜头';ws.append(['时间轴','画面','原文与翻译','镜头及剪辑','音效','营销作用','复拍建议','视频文件'])
 for i,(r,c) in enumerate(zip(rows,clips)):ws.append(r+[c['detail'].get('reshoot','未分析'),f'shot_{i+1:03}.mp4'])
 for col,width in zip('ABCDEFGH',[18,55,55,42,25,42,55,25]):ws.column_dimensions[col].width=width
 for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='D92C55')
 for row in ws.iter_rows(min_row=2):
  for c in row:c.alignment=Alignment(wrap_text=True,vertical='top')
 ws.freeze_panes='B2'; m=w.create_sheet('诊断与数据'); m.append(['项目','结果']);
 for k,v in {**meta,**summary,'状态':result['note']}.items():m.append([k,v])
 m.column_dimensions['A'].width=24;m.column_dimensions['B'].width=100; w.save(folder/'report.xlsx')
 def srt_time(t):
  ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
 (folder/'transcript.srt').write_text('\n\n'.join(f'{i+1}\n{srt_time(s["start"])} --> {srt_time(s["end"])}\n{s["text"]}' for i,s in enumerate(transcript)),encoding='utf-8')
 (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 with zipfile.ZipFile(folder/'export.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in folder.iterdir():
   if p.name!='export.zip' and not p.name.startswith('source.') and p.name!='upload.bin':z.write(p,p.name)
 return result

def jobrun(id,folder,link,upload,ai,asr):
 job=JOBS[id]
 try:
  if link:job['stage']='正在访问TikTok公开页面并获取视频'; path,meta=acquire(link,folder)
  else:path=upload;meta={'name':'本地上传视频','source':'本地视频（无平台指标）'}
  job['result']=process(path,folder,meta,job,ai,asr); job['status']='done';job['stage']='处理结束'
 except Exception as e:job.update(status='failed',stage='处理失败',error=str(e)[-900:])
class Handler(SimpleHTTPRequestHandler):
 def reply(self,status,data):
  b=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin','*') if self.headers.get('Origin') in ALLOWED_ORIGINS or '*' in ALLOWED_ORIGINS else 'null');self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_OPTIONS(self):
  self.send_response(204);self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin','*') if self.headers.get('Origin') in ALLOWED_ORIGINS or '*' in ALLOWED_ORIGINS else 'null');self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type');self.end_headers()
 def do_GET(self):
  if self.path=='/api/health':
   ollama=False
   try:
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2) as r:ollama=any(x['name']==MODEL for x in json.load(r).get('models',[]))
   except Exception:pass
   return self.reply(200,{'ok':True,'service':'tk-studio-v7-fix','configured':ollama,'model':MODEL,'ffmpeg':bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),'collector':bool(importlib.util.find_spec('yt_dlp')),'whisper':bool(importlib.util.find_spec('faster_whisper'))})
  if re.fullmatch(r'/api/jobs/[a-f0-9]{32}',self.path):
   j=JOBS.get(self.path.split('/')[-1]);return self.reply(200 if j else 404,j or {'error':'任务不存在'})
  if self.path in ('/','/index.html') or re.fullmatch(r'/media/[a-f0-9]{32}/(?:original\.mp4|shot_\d+\.mp4|frame_\d+_\d+\.jpg|report\.xlsx|export\.zip|transcript\.srt|report\.json)',self.path):return super().do_GET()
  self.send_error(404)
 def do_POST(self):
    try:
     origin=self.headers.get('Origin')
     local_origins=(None,f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
     if origin not in local_origins and '*' not in ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS:return self.reply(403,{'error':'当前来源未加入 ALLOWED_ORIGINS'})
     n=int(self.headers.get('Content-Length','0')); route=urlsplit(self.path)
     if not 0<n<=MAX_UPLOAD:return self.reply(413,{'error':f'请求大小限制{MAX_UPLOAD//1000000}MB'})
     if route.path=='/api/generate':
      d=json.loads(self.rfile.read(n));return self.reply(200,local_ai('生成原创短视频拍摄脚本，使用真实产品资料，禁止虚构功效。输出JSON scripts数组，每项 name 和 rows（六列：时间、画面、台词及中文、镜头、建议音效、目的）。输入：'+json.dumps(d,ensure_ascii=False)))
     if route.path not in ('/api/link','/api/upload'):return self.reply(404,{'error':'未知接口'})
     if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise ValueError('请先安装 FFmpeg')
     if any(j['status']=='running' for j in JOBS.values()):return self.reply(409,{'error':'已有任务运行，请完成后重试'})
     id=uuid.uuid4().hex;folder=MEDIA/id;folder.mkdir();link=None;upload=None;ai=True;asr=True
     if route.path=='/api/link':
      d=json.loads(self.rfile.read(n));link=d['url'];ai=bool(d.get('ai',True));asr=bool(d.get('asr',True))
      if not d.get('permission'):raise ValueError('请确认有权下载及分析视频')
     else:
      from urllib.parse import parse_qs
      q=parse_qs(route.query);ai=q.get('ai',['1'])[0]=='1';asr=q.get('asr',['1'])[0]=='1';upload=folder/'upload.bin';upload.write_bytes(self.rfile.read(n))
     JOBS[id]={'status':'running','stage':'任务已创建'};threading.Thread(target=jobrun,args=(id,folder,link,upload,ai,asr),daemon=True).start();self.reply(202,{'id':id})
    except Exception as e:self.reply(400,{'error':str(e)[:500]})
if __name__=='__main__':
  import webbrowser
  if os.getenv('HOST'):
   server=ThreadingHTTPServer((os.getenv('HOST','0.0.0.0'),PORT),Handler)
  else:
   for port in range(8768,8790):
    try:
     server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
     break
    except OSError: continue
   else: raise RuntimeError('All TK Studio ports 8768-8789 are busy')
  address=f'http://{server.server_address[0]}:{server.server_port}/'
  print('TK Studio ready: '+address,flush=True)
  if '--open-browser' in sys.argv: threading.Timer(1.0,lambda:webbrowser.open(address)).start()
  (ROOT/'current-address.txt').write_text(address,encoding='utf-8')
  server.serve_forever()
