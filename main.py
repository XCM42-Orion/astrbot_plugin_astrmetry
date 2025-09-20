from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger # 使用 astrbot 提供的 logger 接口
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
import os
import sys
import time
import base64
import shutil
import http.cookiejar
import requests
import json
import re
from PIL import Image

def submit_file(file_path, file_name,apisession, **params):
        # 注:file_name应与file_path中的文件名一致,带扩展名
        headers = {
            "MIME-Version": "1.0"
        }
        # 默认值
        json_data = {
            "session": apisession,
            "publicly_visible": "y",
            "allow_modifications": "d",
            "allow_commercial_use": "d"
        }
        # 其他参数请参考: http://astrometry.net/doc/net/api.html
        json_data.update(params)
        files = {
            "request-json": (
                None,  # 参数名
                json.dumps(json_data),
                'text/plain',  # Content-Type 设置为 text/plain
                {
                    'Content-disposition': 'form-data; name="request-json"'
                }
            ),
            "file": (
                file_name,
                open(file_path, 'rb'),
                'application/octet-stream',  # Content-Type 设置为 application/octet-stream
                {
                    'Content-disposition': f'form-data; name="file"; filename="{file_name}"'
                }
            )
        }
        response = requests.post('http://nova.astrometry.net/api/upload', files=files, headers=headers)
        subid = response.text.split('id": ')[-1].split(',')[0]
        return subid

def check_submission(subid):
        count = 0
        while count < 100:
            response = requests.get(f'http://nova.astrometry.net/api/submissions/{subid}')
            if not any(char.isdigit() for char in response.text.split('jobs": ')[-1].split(',')[0]):
                time.sleep(0.5)
                count += 1
            else:
                break
        if count > 99:
            logger.info('Astrometry.net 查询提交结果超时...')
        jobid = response.text.split('jobs": [')[-1].split(']')[0]
        logger.info('提交成功！返回的JOBID:'+jobid)
        return jobid

def check_job_completion(jobid):
        count = 0
        while count < 100:
            response = requests.get(f'http://nova.astrometry.net/api/jobs/{jobid}')
            if 'success' not in response.text:
                time.sleep(1)
                count += 1
            else:
                break
        if count > 99:
            logger.info('Astrometry.net 查询解析结果超时...')
        logger.info("解析完成！")


@register("astrbot_plugin_astrmetry", "M42", "接入Astrometry.net进行星空图解析", "1.1", "https://github.com/XCM42-Orion/astrbot_plugin_astrmetry")
class MyPlugin(Star):
    def __init__(self, context: Context,config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.APIkey: str = config.get("APIkey", "")
        print(self.config)

    @filter.command("解析")
    async def donate(self, event: AstrMessageEvent):
        '''发送星空图进行解析''' 
        user_name = event.get_sender_name()
        message_str = event.message_str # 获取消息的纯文本内容
        logger.info(f"{user_name}执行了解析...")
        messages = event.get_messages()
        img_url = None
        for seg in messages:
            if isinstance(seg, Comp.Image):
                img_url = seg.url
                break
            elif isinstance(seg, Comp.Reply):
                if seg.chain:
                    for reply_seg in seg.chain:
                        if isinstance(reply_seg, Comp.Image):
                            img_url = reply_seg.url
                            break
        sourseimg = requests.get(img_url)
        with open('sourseimage.jpg', 'wb') as file:
            file.write(sourseimg.content)
        R = requests.post('http://nova.astrometry.net/api/login', data={'request-json': json.dumps({"apikey": self.APIkey})})    #获取session
        pattern = r"(?<=(session\"\:\s\"))([0-9]|[a-z])+([0-9]|[a-z])"
        apisession = re.search(pattern,R.text).group()  #从返回值当中提取session
        imgpath = os.path.abspath('sourseimage.jpg')  #输入要上传的图像路径
        imgname = "sourseimage.jpg"
        subid = submit_file(file_path = imgpath, file_name = imgname,apisession = apisession)   #提交文件
        yield event.plain_result('提交成功！提交的SUBID:'+subid)
        jobid = check_submission(subid=subid)  #检查提交情况
        yield event.plain_result('提交成功！提交的JOBID:'+jobid)
        check_job_completion(jobid=jobid)  #检查完成情况
        urlinfo = f"http://nova.astrometry.net/api/jobs/{jobid}/info/"
        urlanno = f"http://nova.astrometry.net/annotated_display/{jobid}.jpg"

        for trytimes1 in range(1,100) :   #尝试得到解析数据
            responseinfo = requests.get(urlinfo)
            if responseinfo.status_code == 200:
                logger.info("成功获取解析数据："+responseinfo.text)
                break
            if trytimes1 == 99:
                yield event.plain_result("获取解析数据超时...")
        objects = re.search(r"(?<=(\"objects_in_field\":))\s*\[(.*?)\]",responseinfo.text).group()
        ra = re.search(r"(?<=(\"ra\":))\s*([\d\.-]+)",responseinfo.text).group()
        dec = re.search(r"(?<=(\"dec\":))\s*([\d\.-]+)",responseinfo.text).group()
        rad = re.search(r"(?<=(\"radius\":))\s*([\d\.-]+)",responseinfo.text).group()
        psc = re.search(r"(?<=(\"pixscale\":))\s*([\d\.-]+)",responseinfo.text).group()

        for trytimes2 in range(1,100) :   #尝试下载图片文件
            responsefile = requests.get(urlanno)
            if responsefile.status_code == 200:
                chain = [
                    Comp.At(qq=event.get_sender_id()), # At 消息发送者
                    Comp.Plain(" 解析成功！\nsubid:"+subid+",jobid:"+jobid+"\n"),
                    Comp.Plain("解析结果：\n画面中目标："+objects+"\n中心赤经："+ra+"\n中心赤纬："+dec+"\n范围："+rad+"°"+"\n像素尺寸："+psc+"arcsec/pixel\n"+"标注图像链接：" +urlanno)
                ]
                yield event.chain_result(chain)
                break
            if trytimes2 == 99:
                yield event.plain_result("标注图像生成失败...")
            time.sleep(1)




