from django.shortcuts import render
from django.http import JsonResponse
from books.models import Books
from utils.decorators import login_required
from django_redis import get_redis_connection
# Create your views here.
def cart_add(request):
    '''向购物车中添加数据'''
    # 判断用户是否登录
    if not request.session.has_key('islogin'):
        return JsonResponse({'res':0, 'errmsg':'请先登录'})

    # 接收数据
    books_id = request.POST.get('books_id')
    books_count = request.POST.get('books_count')

    # 进行数据校验
    if not all([books_id, books_count]):
        return JsonResponse({'res':1 , 'errmsg':'数据不完整'})

    books = Books.objects.get_books_by_id(books_id=books_id)
    if books is None:
        # 商品不存在
        return JsonResponse({'res':2, 'errmsg':'商品不存在'})

    try:
        count = int(books_count)
    except Exception as e:
        # 商品数目不合法
        return JsonResponse({'res':3, 'errmsg':'商品数量必须为数字'})

    # 添加商品到购物车
    # 每个用户的购物车记录用一条hash数据保存，格式:cart_用户id: 商品id 商品数量
    conn = get_redis_connection('default')
    cart_key = 'cart_%d' % request.session.get('passport_id')

    res = conn.hget(cart_key, books_id)
    if res is None:
        # 如果用户的购车中没有添加过该商品，则添加数据
        res = count
    else:
        # 如果用户的购车中已经添加过该商品，则累计商品数目
        res = int(res) + count

    # 判断商品的库存
    if res > books.stock:
        # 库存不足
        return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})
    else:
        conn.hset(cart_key, books_id, res)

    # 返回结果
    return JsonResponse({'res': 5})

def cart_count(request):
    '''获取用户购物车中商品的数目'''
    # 判断用户是否登录
    if not request.session.has_key('islogin'):
        return JsonResponse({'res': 0})

    # 计算用户购物车商品的数量
    conn = get_redis_connection('default')
    cart_key = 'cart_%d' % request.session.get('passport_id')
    # res = conn.hlen(cart_key) 显示商品的条目数
    res = 0
    res_list = conn.hvals(cart_key)

    for i in res_list:
        res += int(i)

    # 返回结果
    return JsonResponse({'res': res})


def cart_show(request):
    '''显示用户购物车页面'''
    passport_id = request.session.get('passport_id')
    # 获取用户购物车的记录
    conn = get_redis_connection('default')
    cart_key = 'cart_' + str(passport_id)
    res_dict = conn.hgetall(cart_key)

    books_li = []
    # 保存所有商品的总数
    total_count = 0
    # 保存所有商品的总价格
    total_price = 0

    # 遍历res_dict获取商品的数据
    for id, count in res_dict.items():
        # 根据id获取商品的信息
        books = Books.objects.get_books_by_id(books_id=id)
        # 保存商品的数目
        books.count = count
        # 保存商品的小计
        books.amount = int(count)*books.price

        books_li.append(books)

        total_count += int(count)
        total_price += int(count)*books.price

        context = {
            'books_li': books_li,
            'total_count': total_count,
            'total_price': total_price
        }
        return render(request, 'cart/cart.html', context)


def cart_del(request):
    '''删除用户购物车中商品的信息'''
    # 判断用户是否登录
    if not request.session.has_key('islogin'):
        return JsonResponse({'res': 500, 'errmsg':'请先登录'})

    # 接收数据
    books_id = request.POST.get('books_id')
    