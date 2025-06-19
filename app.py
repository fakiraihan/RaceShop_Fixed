import datetime
import uuid
import os
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from flask import Flask, request, render_template, make_response, redirect

from peewee import *

db = SqliteDatabase("b.db")

db_lock = threading.Lock()


class User(Model):
    id = AutoField()
    username = CharField(unique=True)
    password = CharField()
    token = CharField()
    balance = IntegerField()

    class Meta:
        database = db


class PurchaseLog(Model):
    id = AutoField()
    user_id = IntegerField()
    product_id = IntegerField()
    paid_amount = IntegerField()
    v_date = DateField(default=datetime.datetime.now)

    class Meta:
        database = db


class Product(Model):
    id = AutoField()
    name = CharField(unique=True)
    price = IntegerField()

    class Meta:
        database = db


@db.connection_context()
def initialize():
    db.create_tables([User, PurchaseLog, Product])
    for i in [
        {
            "name": "Galois Salad", "price": 5,
        },
        {
            "name": "Alpaca Salad", "price": 20,
        },
        {
            "name": "Flag", "price": 21,
        }
    ]:
        try:
            Product.create(name=i["name"], price=i["price"])
        except:
            pass


initialize()


class API:
    @staticmethod
    @db.connection_context()
    def login(username, password) -> str:
        user_objs = User \
            .select() \
            .where(User.username == username)
        if len(user_objs) == 0:
            token = str(uuid.uuid4())
            try:
                User.create(
                    username=username,
                    password=password,
                    token=token,
                    balance=20,
                )
            except IntegrityError as e:
                print(e)
                return ""
            return token
        user_obj = user_objs[0]
        if user_obj.password != password:
            return ""
        return user_obj.token

    @staticmethod
    @db.connection_context()
    def get_user_detail_by_token(token: str) -> (bool, int, [PurchaseLog]):
        user_objs = User \
            .select() \
            .where(User.token == token)
        if len(user_objs) == 0:
            return False, 0, None
        user_obj = user_objs[0]
        purchase_log = PurchaseLog \
            .select() \
            .where(PurchaseLog.user_id == user_obj.id)
        return True, user_obj.balance, [x for x in purchase_log]

    @staticmethod
    @db.connection_context()
    def buy(product_id: int) -> (bool, str):
        with db_lock:
            # get product pricing
            product_objs = Product \
                .select() \
                .where(Product.id == product_id)
            if len(product_objs) == 0:
                return False, "No such product"
            product_obj = product_objs[0]

            user_objs = User \
                .select()
            if len(user_objs) == 0:
                return False, "Wrong Token"
            user_obj = user_objs[0]

            logging.info(f"[BUY] User {user_obj.username} balance before: {user_obj.balance}, product price: {product_obj.price}")

            if product_obj.price > user_obj.balance:
                return False, "No money you have bro..."
            try:
                PurchaseLog.create(
                    user_id=user_obj.id,
                    product_id=product_obj.id,
                    paid_amount=product_obj.price
                )
            except IntegrityError as e:
                print(e)
                return False, "System error"

            User\
                .update(balance=user_obj.balance - product_obj.price)\
                .where(User.id == user_obj.id)\
                .execute()
            
            logging.info(f"[BUY] User {user_obj.username} balance after: {user_obj.balance - product_obj.price}")

            return True, ""

    @staticmethod
    @db.connection_context()
    def sell(purchase_id: int) -> (bool, str):
        with db_lock:    
            purchase_history_objs = PurchaseLog \
                .select() \
                .where(PurchaseLog.id == purchase_id)
            if len(purchase_history_objs) == 0:
                return False, "No such product"
            purchase_history_obj = purchase_history_objs[0]

            user_objs = User \
                .select()
            if len(user_objs) == 0:
                return False, "Wrong Token"

            user_obj = user_objs[0]

            logging.info(f"[SELL] User {user_obj.username} balance before: {user_obj.balance}, refund: {purchase_history_obj.paid_amount}")


            if purchase_history_obj.user_id != user_obj.id:
                return False, "Not the purchase you made bro..."

            PurchaseLog\
                .delete()\
                .where(PurchaseLog.id == purchase_history_obj.id)\
                .execute()

            User \
                .update(balance=user_obj.balance + purchase_history_obj.paid_amount) \
                .where(User.id == user_obj.id) \
                .execute()
            
            logging.info(f"[SELL] User {user_obj.username} balance after: {user_obj.balance + purchase_history_obj.paid_amount}")

            if purchase_history_obj.paid_amount == 21:
                return False, f"Well, flag is {os.getenv('FLAG')}"
            return True, ""


app = Flask(__name__)


@app.route('/', methods=["GET", "POST"])
def default():
    if request.method == 'POST':
        token = API.login(request.form["username"], request.form["password"])
        if token:
            resp = make_response(redirect("/"))
            resp.set_cookie("token", token)
            return resp
        else:
            return render_template('login.html',
                                   error_msg="Wrong credential")
        pass
    else:
        token = request.cookies.get("token")

        def go_login():
            return render_template('login.html')

        if token and len(token) > 5:
            is_login, balance, purchase_log = API.get_user_detail_by_token(token)
            if not is_login:
                resp = make_response(redirect("/"))
                resp.set_cookie("token", "")
                return resp
            return render_template('home.html', balance=balance, purchase_log=purchase_log)
        return go_login()


@app.route('/buy/<product_id>', methods=["GET"])
def buy(product_id):
    is_success, err_message = API.buy(int(product_id))
    if is_success:
        return make_response(redirect("/"))
    else:
        return err_message


@app.route('/sell/<purchase_id>', methods=["GET"])
def sell(purchase_id):
    is_success, err_message = API.sell(int(purchase_id))
    if is_success:
        return make_response(redirect("/"))
    else:
        return err_message


