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
import aiohttp
import asyncio
import aiofiles


async def submit_file(file_path, file_name,apisession,session, **params):
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
    # 使用 FormData 来构建请求数据
    # 创建 FormData 对象
        form = aiohttp.FormData()
    
    # 将 JSON 数据添加到 form 中，MIME 类型设置为 'text/plain'
        form.add_field('request-json', json.dumps(json_data), content_type='text/plain')
    
        try:
        # 读取文件内容，并将文件数据保持在内存中
            async with aiofiles.open(file_path, 'rb') as file:
                file_content = await file.read()  # 读取文件内容到内存
                form.add_field('file', file_content, filename=file_name, content_type='application/octet-stream')
        
        # 发送 POST 请求
            async with session.post('http://nova.astrometry.net/api/upload', data=form, headers=headers) as response:
                try:
                    data = await response.text()
        
        # 从返回的文本中解析出 subid
                    subid = str(json.loads(data)["subid"])
                    return subid
                except(json.JSONDecodeError,KeyError)as e:
                     logger.error(f"解析subid失败：{e}")
    
        except Exception as e:
            print(f"上传文件时出错: {e}")
            return None

async def check_submission(subid,session):
        count = 0
        while count < 100:
                async with session.get(f'http://nova.astrometry.net/api/submissions/{subid}') as response:
                    response_text = await response.text()
                    if not any(char.isdigit() for char in response_text.split('jobs": ')[-1].split(',')[0]):
                        await asyncio.sleep(0.5)
                        count += 1
                    else:
                        break
        if count > 99:
            logger.error('Astrometry.net 查询提交结果超时...')
        jobs = json.loads(response_text)["jobs"]
        jobid = str(jobs[0])
        logger.info('提交成功！返回的JOBID:'+jobid)
        return jobid

async def check_job_completion(jobid,session):
        count = 0
        while count < 100:
                async with session.get(f'http://nova.astrometry.net/api/jobs/{jobid}') as response:
                    response_text = await response.text()
                    if 'success' not in response_text:
                        await asyncio.sleep(0.5)
                        count += 1
                    else:
                        logger.info("解析完成！")
                        break
        if count > 99:
            logger.error('Astrometry.net 查询解析结果超时...')


@register("astrbot_plugin_astrmetry", "M42", "接入Astrometry.net进行星空图解析", "1.0", "https://github.com/XCM42-Orion/astrbot_plugin_astrmetry")
class MyPlugin(Star):
    def __init__(self, context: Context,config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.APIkey: str = config.get("APIkey", "")
        print(self.config)

    @filter.command("解析")
    async def analyse(self, event: AstrMessageEvent):
        '''发送星空图进行解析''' 
        async with aiohttp.ClientSession() as session:
            user_name = event.get_sender_name()
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
            data = {"apikey": self.APIkey}
            # 将 JSON 对象转换成 URL 编码的字符串
            encoded_data = {'request-json': json.dumps(data)}
            async with session.post('http://nova.astrometry.net/api/login', data=encoded_data) as response:
                R = await response.text()  # 获取响应内容
            apisession = json.loads(R)["session"]  #从返回值当中提取session
            imgpath = os.path.abspath('sourseimage.jpg')  #输入要上传的图像路径
            imgname = "sourseimage.jpg"
            subid = await submit_file(file_path = imgpath, file_name = imgname,apisession = apisession,session=session)   #提交文件
            yield event.plain_result('提交成功！提交的SUBID:'+subid)
            jobid = await check_submission(subid=subid,session=session)  #检查提交情况
            yield event.plain_result('提交成功！提交的JOBID:'+jobid)
            await check_job_completion(jobid=jobid,session=session)  #检查完成情况
            urlinfo = f"http://nova.astrometry.net/api/jobs/{jobid}/info/"
            urlanno = f"http://nova.astrometry.net/annotated_display/{jobid}.jpg"

            for trytimes1 in range(1, 100):  # 尝试获取解析数据
                async with session.get(urlinfo) as responseinfo:
                    if responseinfo.status == 200:  # 正确的状态码检查
                # 获取响应体并输出
                        response_text = await responseinfo.text()
                        logger.info(f"成功获取解析数据：{response_text}")
                        break
                    await asyncio.sleep(0.5)  # 等待一段时间再重试
                    if trytimes1 == 99:
                # 超过 99 次还没成功则返回超时提示
                        yield event.plain_result("获取解析数据超时...")
            rjs = json.loads(response_text)
            objects = str(rjs["objects_in_field"])
            ra = str(rjs["calibration"]["ra"])
            dec = str(rjs["calibration"]["dec"])
            rad = str(rjs["calibration"]["radius"])
            psc = str(rjs["calibration"]["pixscale"])

            for trytimes2 in range(1,100) :   #尝试下载图片文件
                    async with session.get(urlanno) as responsefile:
                        if responsefile.status == 200:
                            chain = [
                                Comp.At(qq=event.get_sender_id()), # At 消息发送者
                                Comp.Plain(" 解析成功！\nsubid:"+subid+",jobid:"+jobid+"\n"),
                                Comp.Plain("解析结果：\n画面中目标："+objects+"\n中心赤经："+ra+"\n中心赤纬："+dec+"\n范围："+rad+"°"+"\n像素尺寸："+psc+"arcsec/pixel\n"+"标注图像链接：" +urlanno)
                            ]
                            yield event.chain_result(chain)
                            break
                        await asyncio.sleep(0.5)
                        if trytimes2 == 99:
                            yield event.plain_result("标注图像生成失败...")
        await session.close() 
