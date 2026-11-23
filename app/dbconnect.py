import os
import pymysql
  
db= pymysql.connect(host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
                     port=int(os.environ.get('MYSQL_PORT', '3306')),
                     user=os.environ.get('MYSQL_USER', ''),
                     passwd=os.environ.get('MYSQL_PASSWORD', ''),
                     db='mysql',
                     charset='utf8mb4')
try:
    with db.cursor() as cursor:
        sql= """
            select 1 from mysql.user limit 1'
            """
        cursor.execute(sql)
        result = cursor.fetchall()
        print(result)
finally:
    db.close()
