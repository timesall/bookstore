from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from users.models import Passport,Address
from books.models import Books
from django.views.decorators.csrf import csrf_exempt
import json
from django.core.mail import send_mail
from django.http import JsonResponse
from utils.decorators import login_required
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from bookstore import settings
from order.models import OrderGoods, OrderInfo
from django.http import HttpResponse
from PIL import Image, ImageDraw, ImageFont # 引入绘图模块
from django_redis import get_redis_connection
import random

# Create your views here.


def register(request):
    return render(request, 'users/register.html')


# 由前端传回来的表单数据
@csrf_exempt
def register_handle(request):
    # 接收数据
    data = json.loads(request.body.decode('utf-8'))

    username = data.get('username', '')
    # 判断邮箱是否合法 TODO
    # 判断用户名是否重复
    p = Passport.objects.get_only_name(username)
    if not p:
        # 返回登录页
        # return redirect(reverse('user:login'))
        return JsonResponse({'res': 1})
    return JsonResponse({'res': 500})


@csrf_exempt
def register_done(request):
    # 接收数据
    data = json.loads(request.body.decode('utf-8'))

    username = data.get('username', '')
    password = data.get('password', '')
    email = data.get('email', '')
    # 进行数据校验
    if not all([username, password, email]):
        # 有空的数据
        return JsonResponse({'res': 500})

    # 向系统中添加账户
    passport = Passport.objects.add_one_passport(username=username, password=password, email=email)
    # 生成激活的token itsdangerous
    serializer = Serializer(settings.SECRET_KEY, 3600)
    token = serializer.dumps({'confirm': passport.id}) # 返回bytes
    token = token.decode()
    # 给用户的邮箱发激活邮件
    send_mail('尚硅谷书城用户激活', '', settings.EMAIL_FROM, [email], html_message='<a href="http://127.0.0.1:8001/user/active/%s/">http://127.0.0.1:8001/user/active/</a>' % token)
    # 返回登录页
    # return redirect(reverse('user:login'))
    return JsonResponse({'res': 1})


def login(request):
    # 判断cookie中是否有username
    if 'username' in request.COOKIES:
        context = {
            'username': request.COOKIES['username'],
            'checked': 'checked'
        }
    else:
        context = {
            'username': '',
            'password': '',
        }
    return render(request, 'users/login.html', context)


@csrf_exempt
def login_check(request):
    # username = request.POST.get('username')
    # password = request.POST.get('pwd')
    # remember = request.POST.get('remember')
    data = json.loads(request.body.decode('utf-8'))
    username = data.get('username', '')
    password = data.get('password', '')
    remember = data.get('remember', '')
    verifycode = data.get('verifycode', '')
    if not all([username, password, verifycode]):
        return JsonResponse({'res': 499})
    if verifycode.upper() != request.session['verifycode']:
        return JsonResponse({'res': 499})

    # 查找账户信息
    passport = Passport.objects.get_one_passport(username, password)
    # 验证通过
    if passport:
        # next_url = request.session.get('url_path', reverse('books:index'))
        next_url = reverse('books:index')
        jres = JsonResponse({'res': 1, 'next_url': next_url})
        # 是否记住用户名
        if remember:
            jres.set_cookie('username', username, max_age=7*24*3600)
        else:
            jres.delete_cookie('username')
        # 记住登录状态
        request.session['islogin'] = True
        request.session['username'] = username
        request.session['passport_id'] = passport.id
        # 返回json串
        return jres
    else:
        # 用户或密码错误
        p = Passport.objects.get_only_name(username)
        if not p:
            # 用户名不存在
            return JsonResponse({'res': 500})
        # 密码错误
        return JsonResponse({'res': 501})


def logout(request):
    # 清空session信息
    request.session.flush()
    # 重定向到首页
    return redirect(reverse('books:index'))


@login_required
def user(request):
    '''用户中心-信息页'''
    passport_id = request.session.get('passport_id')
    # 获取用户的基本信息
    addr = Address.objects.get_default_address(passport_id=passport_id)
    # 获取用户的最近浏览信息
    con = get_redis_connection('default')
    key = 'history_%d'%passport_id
    # 取出用户最近浏览为各商品的id
    history_li = con.lrange(key, 0, 4)

    books_li = []
    for id in history_li:
        books = Books.objects.get_books_by_id(books_id=id)
        books_li.append(books)
    context = {
        'addr': addr,
        'page': 'user',
        'books_li': books_li
    }

    return render(request, 'users/user_center_info.html', context)


def address(request):
    '''用户中心-收货地址'''
    # 获取登录用户的id
    passport_id = request.session.get('passport_id')
    if request.method == 'GET':
        # 查询用户的默认地址
        addr = Address.objects.get_default_address(passport_id=passport_id)
        return render(request, 'users/user_center_site.html', {'addr': addr, 'page': 'address'})
    else:
        # 添加收货地址
        # 1.接收数据
        recipent_name = request.POST.get('username')
        recipent_addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        recipent_phone = request.POST.get('phone')
        # 2.进行校验
        if not all([recipent_name, recipent_addr, zip_code, recipent_phone]):
            return render(request, 'users/user_center_site.html', {'errmsg': '参数不能为空'})
        # 3.添加收货地址
        Address.objects.add_one_address(passport_id=passport_id,
                                        recipient_name=recipent_name,
                                        recipient_addr=recipent_addr,
                                        zip_code=zip_code,
                         recipient_phone=recipent_phone)
        # 4.返回应答
        return redirect(reverse('user:address'))

@login_required
def order(request):
    '''全部订单页面'''
    # 查询用户的订单信息
    passport_id = request.session.get('passport_id')
    # 获取订单信息
    order_li = OrderInfo.objects.filter(passport_id=passport_id)
    # 遍历获取订单的商品信息
    # order -> OrderInfo实例对象
    for order in order_li:
        order_id = order.order_id
        order_books_li = OrderGoods.objects.filter(order_id=order_id)
        # 计算商品的小计
        # order_books -> OrderBooks实例对象
        for order_books in order_books_li:
            count = order_books.count
            price = order_books.price
            amount = count * price
            # 保存订单中每一个商品的小计
            order_books.amount = amount
        # 给order对象动态增加一个属性order_goods_li，保存订单中商品的信息
        order.order_books_li = order_books_li
        context = {
            'order_li': order_li,
            'page': 'order'
        }
        return render(request, 'users/user_center_order.html', context)


def verifycode(request):
    # 定义变量，用于画面的背景色、宽、高
    bgcolor = (random.randrange(20, 100), random.randrange(20, 100), 255)
    width = 100
    height = 25
    # 创建画面对象
    im = Image.new('RGB', (width, height), bgcolor)
    # 创建画笔对象
    draw = ImageDraw.Draw(im)
    # 调用画笔的point()函数绘制噪点
    for i in range(0, 100):
        xy = (random.randrange(0, width), random.randrange(0, height))
        fill = (random.randrange(0, 255), 255, random.randrange(0, 255))
        draw.point(xy, fill=fill)
    # 定义验证码的备选值
    str1 = 'ABCD123EFGHIJK456LMNOPQRS789TUVWXYZ0'
    # 随机选取4个值作为验证码
    rand_str = ''
    for i in range(0, 4):
        rand_str += str1[random.randrange(0, len(str1))]
    # 构造字体对象
    font = ImageFont.truetype("/usr/share/fonts/freefont/FreeMonoBoldOblique.ttf", 15)
    # 构造字体颜色
    fontcolor = (255, random.randrange(0, 255), random.randrange(0, 255))
    # 绘制4个字
    draw.text((5, 2), rand_str[0], font=font, fill=fontcolor)
    draw.text((25, 2), rand_str[1], font=font, fill=fontcolor)
    draw.text((50, 2), rand_str[2], font=font, fill=fontcolor)
    draw.text((75, 2), rand_str[3], font=font, fill=fontcolor)
    # 释放画笔
    del draw
    # 存入session，用于做进一步验证
    request.session['verifycode'] = rand_str
    # 内存文件操作
    import io
    buf = io.BytesIO()
    # 将图片保存在内存中，文件类型为png
    im.save(buf, 'png')
    # 将内存中的图片数据返回给客户端，MIME类型为图片png
    return HttpResponse(buf.getvalue(), 'image/png')


def register_active(requset, token):
    '''用户账户激活'''
    serializer = Serializer(settings.SECRET_KEY, 3600)
    try:
        info = serializer.loads(token)
        passport_id = info['confirm']
        # 进行用户激活
        passport = Passport.objects.get(id=passport_id)
        passport.is_active = True
        passport.save()
        # 跳转到登录页
        return redirect(reverse('user:login'))
    except SignatureExpired:
        # 链接过期
        return HttpResponse('激活链接已过期')
