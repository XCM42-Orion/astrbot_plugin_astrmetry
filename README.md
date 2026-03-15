# astrbot_plugin_astrmetry  by M42
版本v1.2  
基于Astrometry.net进行星空图解析。  

使用需要先注册Astrometry.net并获取API并配置，主页：nova.astrometry.net  
使用方法：/解析+发送需要解析的图片。可以获得图片中主要天体信息、中心坐标、视场和像素尺寸、标注后图像的链接，以及标注后的图像（如果可以获取）。  
如果出现了超时未完成解析的情况也可以拿astrbot反馈的jobid去nova.astrometry.net手动找结果。未来我会做一个手动找结果的功能。  

***
## 更新日志 ##  

### v1.2
重新设计了获取图片的逻辑，现在可以获取标注后的图片了。

### v1.1
（25/9/20）  
几乎完全重写了代码，把requests全部改成了aiohttp，因此实现了异步作业。现在不用担心bot会卡死了

### v1.0
（25/9/20）  
正式版本。
