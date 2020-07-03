页面采用layui2.5.6构建，修改部分源码和编译，具体如下：

## upload.js源码修改

#### 1. updateData

upload.render增加updateData选项，函数类型，用以更新data

[大概位置](https://github.com/sentsin/layui/blob/master/src/lay/modules/upload.js#L178)
下面几行，在``var formData = new FormData();``上方增加:

```
typeof options.updateData === 'function' &&  options.updateData(index, options.data);
```

#### 2. progress

2.5.5新增此回调，只有一个百分比参数；2.5.6增加一个当前元素DOM对象，但还是不够直接，直接加index

progress选项参数修改，参考上面大概位置再下面几行，监听进度条，百分比后面的：

```
options.progress(percent, options.item[0], e);
改为
options.progress(index, percent, options.item[0], e);
```

## layer.js源码修改

layer.prompt增加placeholder选项，支持三种type

https://github.com/sentsin/layui/blob/master/src/lay/modules/layer.js#L973

## 编译修改

采用all参数，修改gulpfile.js，仅编译部分模块：

```
//模块
,mods = 'laytpl,laypage,laydate,jquery,layer,element,upload,slider,colorpicker,form,tree,transfer,table,carousel,rate,util,flow,layedit,code'
改为
,mods = 'laytpl,laypage,jquery,layer,element,upload,form,table,util,flow'
```
