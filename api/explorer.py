import datetime
import json
import urllib2
import config
import psycopg2
from services.bitshares_websocket_client import BitsharesWebsocketClient

bitshares_ws_client = BitsharesWebsocketClient(config.WEBSOCKET_URL)

def header():
    response = bitshares_ws_client.request('database', 'get_dynamic_global_properties', [])

    core_asset_description = bitshares_ws_client.get_object('2.3.0')

    current_supply = core_asset_description["current_supply"]
    confidental_supply = core_asset_description["confidential_supply"]

    market_cap = int(current_supply) + int(confidental_supply)
    response["bts_market_cap"] = int(market_cap/100000000)

    if config.TESTNET != 1: # Todo: had to do something else for the testnet
        btsBtcVolume = bitshares_ws_client.request('database', 'get_24_volume', ["BTS", "OPEN.BTC"])
        response["quote_volume"] = btsBtcVolume["quote_volume"]
    else:
        response["quote_volume"] = 0

    global_properties = bitshares_ws_client.request('database', 'get_global_properties', [])

    response["commitee_count"] = len(global_properties["active_committee_members"])
    response["witness_count"] = len(global_properties["active_witnesses"])

    return response


def account(account_id):
    return _account(account_id)

def _account(account_id):
    return bitshares_ws_client.request('database', 'get_accounts', [[account_id]])

def account_name(account_id):
    account = _account(account_id)
    return account[0]['name']

def _account_name(account_id):
    account = _account(account_id)
    return account[0]['name']

def account_id(account_name):
    return _account_id(account_name)

def _account_id(account_name):
    account = bitshares_ws_client.request('database', 'lookup_account_names', [[account_name], 0])
    return account[0]['id']

def _enrich_operation(operation, ws_client):
    dynamic_global_properties = ws_client.request('database', 'get_dynamic_global_properties', [])
    operation["accounts_registered_this_interval"] = dynamic_global_properties["accounts_registered_this_interval"]

    # get market cap
    core_asset = ws_client.get_object('2.3.0')
    current_supply = core_asset["current_supply"]
    confidental_supply = core_asset["confidential_supply"]
    market_cap = int(current_supply) + int(confidental_supply)
    operation["bts_market_cap"] = int(market_cap/100000000)

    if config.TESTNET != 1: # Todo: had to do something else for the testnet
        btsBtcVolume = ws_client.request('database', 'get_24_volume', ["BTS", "OPEN.BTC"])
        operation["quote_volume"] = btsBtcVolume["quote_volume"]
    else:
        operation["quote_volume"] = 0

    # TODO: making this call with every operation is not very efficient as this are static properties
    global_properties = ws_client.request('database', 'get_global_properties', [])
    operation["commitee_count"] = len(global_properties["active_committee_members"])
    operation["witness_count"] = len(global_properties["active_witnesses"])

    return [ operation ]

def get_operation(operation_id):
    operation = bitshares_ws_client.get_object(operation_id)
    if not operation:
        operation = {} 

    operation = _enrich_operation(operation, bitshares_ws_client)
    return operation


def operation_full(operation_id):
    # lets connect the operations to a full node
    bitshares_ws_full_client = BitsharesWebsocketClient(config.FULL_WEBSOCKET_URL)

    operation = bitshares_ws_full_client.get_object(operation_id)
    if not operation:
        operation = {} 

    operation = _enrich_operation(operation, bitshares_ws_full_client)
    return operation

def operation_full_elastic(operation_id):
    contents = urllib2.urlopen(config.ES_WRAPPER + "/get_single_operation?operation_id=" + operation_id).read()
    res = json.loads(contents)
    operation = { 
        "op": json.loads(res[0]["operation_history"]["op"]),
        "block_num": res[0]["block_data"]["block_num"], 
        "op_in_trx": res[0]["operation_history"]["op_in_trx"],
        "result": res[0]["operation_history"]["operation_result"], 
        "trx_in_block": res[0]["operation_history"]["trx_in_block"],
        "virtual_op": res[0]["operation_history"]["virtual_op"], 
        "block_time": res[0]["block_data"]["block_time"]
    }

    operation = _enrich_operation(operation, bitshares_ws_client)
    return operation

def accounts():
    core_asset_holders = bitshares_ws_client.request('asset', 'get_asset_holders', ['1.3.0', 0, 100])
    return core_asset_holders


def full_account(account_id):
    account = bitshares_ws_client.request('database', 'get_full_accounts', [[account_id], 0])
    return account


def assets():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT * FROM assets WHERE volume > 0 ORDER BY volume DESC"
    cur.execute(query)
    results = cur.fetchall()
    con.close()
    #print results
    return results


def fees():
    global_properties = bitshares_ws_client.request('database', 'get_global_properties', [])
    return global_properties


def account_history(account_id):
    if not isObject(account_id):
        account_id = _account_id(account_id)

    account_history = bitshares_ws_client.request('history', 'get_account_history', [account_id, "1.11.1", 20, "1.11.9999999999"])

    if(len(account_history) > 0):
        for transaction in account_history:
            creation_block = bitshares_ws_client.request('database', 'get_block_header', [str(transaction["block_num"]), 0])
            transaction["timestamp"] = creation_block["timestamp"]
            transaction["witness"] = creation_block["witness"]
    try:
        return account_history
    except:
        return {}


def get_asset(asset_id):
    return [ _get_asset(asset_id) ]


def _get_asset(asset_id_or_name):
    asset = None
    if not isObject(asset_id_or_name):
        asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[asset_id_or_name], 0])[0]
    else:
        asset = bitshares_ws_client.request('database', 'get_assets', [[asset_id_or_name], 0])[0]

    dynamic_asset_data = bitshares_ws_client.get_object(asset["dynamic_asset_data_id"])
    asset["current_supply"] = dynamic_asset_data["current_supply"]
    asset["confidential_supply"] = dynamic_asset_data["confidential_supply"]
    asset["accumulated_fees"] = dynamic_asset_data["accumulated_fees"]
    asset["fee_pool"] = dynamic_asset_data["fee_pool"]

    issuer = bitshares_ws_client.get_object(asset["issuer"])
    asset["issuer_name"] = issuer["name"]

    return asset


def get_asset_and_volume(asset_id):
    asset = _get_asset(asset_id)

    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT volume, mcap FROM assets WHERE aid=%s"
    cur.execute(query, (asset_id,))
    results = cur.fetchall()
    con.close()
    try:
        asset["volume"] = results[0][0]
        asset["mcap"] = results[0][1]
    except:
        asset[0]["volume"] = 0
        asset[0]["mcap"] = 0

    return [asset]


def block_header(block_num):
    block_header = bitshares_ws_client.request('database', 'get_block_header', [block_num, 0])
    return block_header


def get_block(block_num):
    block = bitshares_ws_client.request('database', 'get_block', [block_num, 0])
    return block


def get_ticker(base, quote):
    return _get_ticker(base, quote)


def _get_ticker(base, quote):
    return bitshares_ws_client.request('database', 'get_ticker', [base, quote])


def get_volume(base, quote):
    return _get_volume(base, quote)


def _get_volume(base, quote):
    return bitshares_ws_client.request('database', 'get_24_volume', [base, quote])


def lastnetworkops():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT * FROM ops ORDER BY block_num DESC LIMIT 10"
    cur.execute(query)
    results = cur.fetchall()
    con.close()

    # add operation data
    for o in range(0, len(results)):
        operation_id = results[o][2]
        object = bitshares_ws_client.get_object(operation_id)
        results[o] = results[o] + tuple(object["op"])

    return results


def get_object(object):
    return [ bitshares_ws_client.get_object(object) ]

def get_asset_holders_count(asset_id):
    return _get_asset_holders_count(asset_id)


def _get_asset_holders_count(asset_id):
    if not isObject(asset_id):
        asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[asset_id], 0])[0]
        asset_id = asset['id']
    return bitshares_ws_client.request('asset', 'get_asset_holders_count', [asset_id])


def get_asset_holders(asset_id, start=0, limit=20):
    if not isObject(asset_id):
        asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[asset_id], 0])[0]
        asset_id = asset['id']
    asset_holders = bitshares_ws_client.request('asset', 'get_asset_holders', [asset_id, start, limit])
    return asset_holders


def get_workers():
    workers_count = bitshares_ws_client.request('database', 'get_worker_count', [])


    # get the votes of worker 114.0 - refund 400k
    refund400k = bitshares_ws_client.get_object("1.14.0")
    thereshold =  int(refund400k["total_votes_for"])

    workers = []
    for w in range(0, workers_count):
        worker = bitshares_ws_client.get_object("1.14." + str(w))
        worker["worker_account_name"] = _account_name(worker["worker_account"])

        current_votes = int(worker["total_votes_for"])
        perc = (current_votes*100)/thereshold
        worker["perc"] = perc

        workers.append([worker])

    r_workers = workers[::-1]
    return filter(None, r_workers)


def isObject(string):
    return len(string.split(".")) == 3

def get_markets(asset_id):
    if not isObject(asset_id):
        asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[asset_id], 0])[0]
        asset_id = asset['id']

    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT * FROM markets WHERE aid=%s"
    cur.execute(query, (asset_id,))
    results = cur.fetchall()
    con.close()
    return results


def get_most_active_markets():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT * FROM markets WHERE volume>0 ORDER BY volume DESC LIMIT 100"
    cur.execute(query)
    results = cur.fetchall()
    con.close()
    return results


def get_order_book(base, quote, limit=False):
    if not limit:
        limit = 10
    elif int(limit) > 50:
        limit = 50
    
    order_book = bitshares_ws_client.request('database', 'get_order_book', [base, quote, limit])
    return order_book


def get_margin_positions(account_id):
    margin_positions = bitshares_ws_client.request('database', 'get_margin_positions', [account_id])
    return margin_positions


def get_witnesses():
    witnesses_count = bitshares_ws_client.request('database', 'get_witness_count', [])

    witnesses = []
    for w in range(0, witnesses_count):
        witness = bitshares_ws_client.get_object("1.6." + str(w))
        if witness:
            witness["witness_account_name"] = _account_name(witness["witness_account"])
            witnesses.append([witness])

    witnesses = sorted(witnesses, key=lambda k: int(k[0]['total_votes']))
    r_witnesses = witnesses[::-1]

    return filter(None, r_witnesses)


def get_committee_members():
    committee_count = bitshares_ws_client.request('database', 'get_committee_count', [])

    committee_members = []
    for w in range(0, committee_count):
        committee_member = bitshares_ws_client.get_object("1.5." + str(w))
        if committee_member:
            committee_member["committee_member_account_name"] = _account_name(committee_member["committee_member_account"])
            committee_members.append([committee_member])

    committee_members = sorted(committee_members, key=lambda k: int(k[0]['total_votes']))
    r_committee = committee_members[::-1] # this reverses array

    return filter(None, r_committee)


def market_chart_dates():
    base = datetime.date.today()
    date_list = [base - datetime.timedelta(days=x) for x in range(0, 100)]
    date_list = [d.strftime("%Y-%m-%d") for d in date_list]
    #print len(list(reversed(date_list)))
    return list(reversed(date_list))


def market_chart_data(base, quote):
    base_asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[base], 0])[0]
    base_id = base_asset["id"]
    base_precision = 10**base_asset["precision"]

    quote_asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[quote], 0])[0]
    quote_id = quote_asset["id"]
    quote_precision = 10**quote_asset["precision"]

    now = datetime.date.today()
    ago = now - datetime.timedelta(days=100)
    market_history = bitshares_ws_client.request('history', 'get_market_history', [base_id, quote_id, 86400, ago.strftime("%Y-%m-%dT%H:%M:%S"), now.strftime("%Y-%m-%dT%H:%M:%S")])

    data = []
    for market_operation in market_history:

        open_quote = float(market_operation["open_quote"])
        high_quote = float(market_operation["high_quote"])
        low_quote = float(market_operation["low_quote"])
        close_quote = float(market_operation["close_quote"])

        open_base = float(market_operation["open_base"])
        high_base = float(market_operation["high_base"])
        low_base = float(market_operation["low_base"])
        close_base = float(market_operation["close_base"])

        open = 1/(float(open_base/base_precision)/float(open_quote/quote_precision))
        high = 1/(float(high_base/base_precision)/float(high_quote/quote_precision))
        low = 1/(float(low_base/base_precision)/float(low_quote/quote_precision))
        close = 1/(float(close_base/base_precision)/float(close_quote/quote_precision))

        ohlc = [open, close, low, high]

        data.append(ohlc)

    append = [0,0,0,0]
    if len(data) < 99:
        complete = 99 - len(data)
        for c in range(0, complete):
            data.insert(0, append)

    return data


def findMax(a,b):
    if a != 'Inf' and b != 'Inf':
        return max([a, b])
    elif a == 'Inf':
        return b
    else:
        return a


def findMin(a, b):
    if a != 0 and b != 0:
        return min([a, b])
    elif a == 0:
        return b
    else:
        return a


def top_proxies():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT sum(amount) FROM holders"
    cur.execute(query)
    total = cur.fetchone()
    total_votes = total[0]

    query = "SELECT voting_as FROM holders WHERE voting_as<>'1.2.5' group by voting_as"
    cur.execute(query)
    proxy_id_rows = cur.fetchall()

    proxies = []

    for proxy_id_row in proxy_id_rows:
        proxy_id = proxy_id_row[0]

        query = "SELECT account_name, amount FROM holders WHERE account_id=%s LIMIT 1"
        cur.execute(query, (proxy_id,))
        proxy_row = cur.fetchone()

        try:
            proxy_name = proxy_row[0]
            proxy_amount = int(proxy_row[1])
        except:
            proxy_name = "unknown"
            proxy_amount = 0

        query = "SELECT amount FROM holders WHERE voting_as=%s"
        cur.execute(query, (proxy_id,))
        follower_rows = cur.fetchall()

        proxy_followers = 0
        for follower_row in follower_rows:
            folower_amount = follower_row[0]
            proxy_amount += int(folower_amount)  # total proxy votes
            proxy_followers += 1

        if proxy_followers > 2:
            proxy_total_percentage = float(float(proxy_amount) * 100.0/ float(total_votes))
            proxies.append([proxy_id, proxy_name, proxy_amount, proxy_followers, proxy_total_percentage])

    con.close()

    proxies = sorted(proxies, key=lambda k: -k[2]) # Reverse amount order

    return proxies


def top_holders():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT * FROM holders WHERE voting_as='1.2.5' ORDER BY amount DESC LIMIT 10"
    cur.execute(query)
    results = cur.fetchall()
    con.close()
    return results


def witnesses_votes():
    proxies = top_proxies()
    proxies = proxies[:10]

    witnesses = get_witnesses()
    witnesses = witnesses[:25]

    w, h = len(proxies) + 2, len(witnesses)
    witnesses_votes = [[0 for x in range(w)] for y in range(h)]

    for w in range(0, len(witnesses)):
        vote_id =  witnesses[w][0]["vote_id"]
        id_witness = witnesses[w][0]["id"]
        witness_account_name = witnesses[w][0]["witness_account_name"]

        witnesses_votes[w][0] = witness_account_name
        witnesses_votes[w][1] = id_witness

        c = 2

        for p in range(0, len(proxies)):
            id_proxy = proxies[p][0]
            proxy = bitshares_ws_client.get_object(id_proxy)
            votes = proxy["options"]["votes"]
            #print votes
            p_vote = "-"
            for v in range(0, len(votes)):

                if votes[v] == vote_id:
                    p_vote = "Y"

            witnesses_votes[w][c] = id_proxy + ":" + p_vote

            c = c + 1

    #print witnesses_votes
    return witnesses_votes


def workers_votes():
    proxies = top_proxies()
    proxies = proxies[:10]

    workers = get_workers()
    workers = workers[:30]
    #print workers

    w, h = len(proxies) + 3, len(workers)
    workers_votes = [[0 for x in range(w)] for y in range(h)]

    for w in range(0, len(workers)):
        vote_id =  workers[w][0]["vote_for"]
        id_worker = workers[w][0]["id"]
        worker_account_name = workers[w][0]["worker_account_name"]
        worker_name = workers[w][0]["name"]

        workers_votes[w][0] = worker_account_name
        workers_votes[w][1] = id_worker
        workers_votes[w][2] = worker_name

        c = 3

        for p in range(0, len(proxies)):
            id_proxy = proxies[p][0]
            proxy = bitshares_ws_client.get_object(id_proxy)
            votes = proxy["options"]["votes"]
            #print votes
            p_vote = "-"
            for v in range(0, len(votes)):

                if votes[v] == vote_id:
                    p_vote = "Y"

            workers_votes[w][c] = id_proxy + ":" + p_vote

            c = c + 1

    #print witnesses_votes
    return workers_votes


def committee_votes():
    proxies = top_proxies()
    proxies = proxies[:10]

    committee = get_committee_members()
    committee = committee[:11]
    #print workers

    w, h = len(proxies) + 2, len(committee)
    committee_votes = [[0 for x in range(w)] for y in range(h)]

    for w in range(0, len(committee)):
        vote_id =  committee[w][0]["vote_id"]
        id_committee = committee[w][0]["id"]
        committee_account_name = committee[w][0]["committee_member_account_name"]

        committee_votes[w][0] = committee_account_name
        committee_votes[w][1] = id_committee

        c = 2

        for p in range(0, len(proxies)):
            id_proxy = proxies[p][0]
            proxy = bitshares_ws_client.get_object(id_proxy)
            votes = proxy["options"]["votes"]

            #print votes
            p_vote = "-"
            if(len(votes) > 0):
            	for v in range(0, len(votes)):

                    if votes[v] == vote_id:
                    	p_vote = "Y"
                    	committee_votes[w][c] = id_proxy + ":" + p_vote
                    	break
                    else:
                    	p_vote = "-"
                    	committee_votes[w][c] = id_proxy + ":" + p_vote

            	c = c + 1
	    else:
		committee_votes[w][c] = id_proxy + ":-"

    #print witnesses_votes
    return committee_votes


def top_markets():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT volume FROM markets ORDER BY volume DESC LIMIT 7"
    cur.execute(query)
    results = cur.fetchall()
    total = 0
    for v in results:
        total = total + v[0]

    query = "SELECT pair, volume FROM markets ORDER BY volume DESC LIMIT 7"
    cur.execute(query)
    results = cur.fetchall()

    w = 2
    h = len(results)
    top_markets = [[0 for x in range(w)] for y in range(h)]

    for tp in range(0, h):
        #print results[tp][1]
        top_markets[tp][0] = results[tp][0]
        #perc = (results[tp][1]*100)/total
        top_markets[tp][1] = results[tp][1]

    con.close()
    return top_markets


def top_smartcoins():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT volume FROM assets WHERE type='SmartCoin' ORDER BY volume DESC LIMIT 7"
    cur.execute(query)
    results = cur.fetchall()
    total = 0
    for v in results:
        total = total + v[0]

    query = "SELECT aname, volume FROM assets WHERE type='SmartCoin' ORDER BY volume DESC LIMIT 7"
    cur.execute(query)
    results = cur.fetchall()

    w = 2
    h = len(results)
    top_smartcoins = [[0 for x in range(w)] for y in range(h)]

    for tp in range(0, h):
        #print results[tp][1]
        top_smartcoins[tp][0] = results[tp][0]
        #perc = (results[tp][1]*100)/total
        top_smartcoins[tp][1] = results[tp][1]

    con.close()
    return top_smartcoins


def top_uias():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT volume FROM assets WHERE type='User Issued' ORDER BY volume DESC LIMIT 7"
    cur.execute(query)
    results = cur.fetchall()
    total = 0
    for v in results:
        total = total + v[0]

    query = "SELECT aname, volume FROM assets WHERE TYPE='User Issued' ORDER BY volume DESC LIMIT 7"
    cur.execute(query)
    results = cur.fetchall()

    w = 2
    h = len(results)
    top_uias = [[0 for x in range(w)] for y in range(h)]

    for tp in range(0, h):
        #print results[tp][1]
        top_uias[tp][0] = results[tp][0]
        #perc = (results[tp][1]*100)/total
        top_uias[tp][1] = results[tp][1]

    con.close()
    return top_uias


def top_operations():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT count(*) FROM ops"
    cur.execute(query)
    results = cur.fetchone()
    total = results[0]

    query = "SELECT op_type, count(op_type) AS counter FROM ops GROUP BY op_type ORDER BY counter DESC"
    cur.execute(query)
    results = cur.fetchall()


    w = 2
    h = len(results)
    top_operations = [[0 for x in range(w)] for y in range(h)]

    for tp in range(0, h):
        #print results[tp][1]
        top_operations[tp][0] = results[tp][0]
        #perc = (results[tp][1]*100)/total
        top_operations[tp][1] = results[tp][1]

    con.close()
    return top_operations


def last_network_transactions():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT * FROM ops ORDER BY block_num DESC LIMIT 20"
    cur.execute(query)
    results = cur.fetchall()
    con.close()
    #print results
    return results


def lookup_accounts(start):
    accounts = bitshares_ws_client.request('database', 'lookup_accounts', [start, 1000])
    return accounts


def lookup_assets(start):
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "SELECT aname FROM assets WHERE aname LIKE %s"
    cur.execute(query, (start+'%',))
    results = cur.fetchall()
    con.close()
    return results


def getlastblocknumber():
    dynamic_global_properties = bitshares_ws_client.request('database', 'get_dynamic_global_properties', [])
    return dynamic_global_properties["head_block_number"]


def account_history_pager(account_id, page):
    if not isObject(account_id):
        account_id = _account_id(account_id)

    # connecting into a full node.
    bitshares_ws_full_client = BitsharesWebsocketClient(config.FULL_WEBSOCKET_URL)

    # need to get total ops for account
    account = bitshares_ws_full_client.request('database', 'get_accounts', [[account_id]])[0]
    statistics = bitshares_ws_full_client.get_object(account["statistics"])

    total_ops = statistics["total_ops"]
    #print total_ops
    start = total_ops - (20 * int(page))
    stop = total_ops - (40 * int(page))

    if stop < 0:
        stop = 0

    if start > 0:
        account_history = bitshares_ws_full_client.request('history', 'get_relative_account_history', [account_id, stop, 20, start])
        for transaction in account_history:
            block_header = bitshares_ws_full_client.request('database', 'get_block_header', [transaction["block_num"], 0])
            transaction["timestamp"] = block_header["timestamp"]
            transaction["witness"] = block_header["witness"]

        return account_history
    else:
        return ""


def account_history_pager_elastic(account_id, page):
    if not isObject(account_id):
        account_id = _account_id(account_id)

    from_ = int(page) * 20
    contents = urllib2.urlopen(config.ES_WRAPPER + "/get_account_history?account_id="+account_id+"&from_="+str(from_)+"&size=20&sort_by=-block_data.block_time").read()

    j = json.loads(contents)

    results = [0 for x in range(len(j))]
    for n in range(0, len(j)):
        results[n] = {"op": json.loads(j[n]["operation_history"]["op"]),
                      "block_num": j[n]["block_data"]["block_num"],
                      "id": j[n]["account_history"]["operation_id"],
                      "op_in_trx": j[n]["operation_history"]["op_in_trx"],
                      "result": j[n]["operation_history"]["operation_result"],
                      "timestamp": j[n]["block_data"]["block_time"],
                      "trx_in_block": j[n]["operation_history"]["trx_in_block"],
                      "virtual_op": j[n]["operation_history"]["virtual_op"]
                      }

    return list(results)


def get_limit_orders(base, quote):
    limit_orders = bitshares_ws_client.request('database', 'get_limit_orders', [base, quote, 100])
    return limit_orders


def get_call_orders(asset_id):
    call_orders = bitshares_ws_client.request('database', 'get_call_orders', [asset_id, 100])
    return call_orders


def get_settle_orders(base, quote):
    settle_orders = bitshares_ws_client.request('database', 'get_settle_orders', [base, quote, 100])
    return settle_orders


def get_fill_order_history(base, quote):
    fill_order_history = bitshares_ws_client.request('history', 'get_fill_order_history', [base, quote, 100])
    return fill_order_history


def get_dex_total_volume():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "select price from assets where aname='USD'"
    cur.execute(query)
    results = cur.fetchone()
    usd_price = results[0]

    query = "select price from assets where aname='CNY'"
    cur.execute(query)
    results = cur.fetchone()
    cny_price = results[0]

    query = "select sum(volume) from assets WHERE aname!='BTS'"
    cur.execute(query)
    results = cur.fetchone()
    volume = results[0]

    query = "select sum(mcap) from assets"
    cur.execute(query)
    results = cur.fetchone()
    market_cap = results[0]
    con.close()

    res = {"volume_bts": round(volume), "volume_usd": round(volume/usd_price), "volume_cny": round(volume/cny_price),
           "market_cap_bts": round(market_cap), "market_cap_usd": round(market_cap/usd_price), "market_cap_cny": round(market_cap/cny_price)}

    return res


def daily_volume_dex_dates():
    base = datetime.date.today()
    date_list = [base - datetime.timedelta(days=x) for x in range(0, 60)]
    date_list = [d.strftime("%Y-%m-%d") for d in date_list]
    #print len(list(reversed(date_list)))
    return list(reversed(date_list))

 
def daily_volume_dex_data():
    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "select value from stats where type='volume_bts' order by date desc limit 60"
    cur.execute(query)
    results = cur.fetchall()

    mod = [0 for x in range(len(results))]
    for r in range(0, len(results)):
        mod[r] = results[r][0]

    return list(reversed(mod))


def get_all_asset_holders(asset_id):
    if not isObject(asset_id):
        asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[asset_id], 0])[0]
        asset_id = asset['id']

    all = []

    asset_holders = bitshares_ws_client.request('asset', 'get_asset_holders', [asset_id, 0, 100])

    all.extend(asset_holders)

    len_result = len(asset_holders)
    start = 100
    while  len_result == 100:
        start = start + 100
        asset_holders = bitshares_ws_client.request('asset', 'get_asset_holders', [asset_id, start, 100])
        len_result = len(asset_holders)
        all.extend(asset_holders)

    return all


def referrer_count(account_id):
    if not isObject(account_id):
        account_id = _account_id(account_id)

    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    query = "select count(*) from referrers where referrer=%s"
    cur.execute(query, (account_id,))
    results = cur.fetchone()

    return results


def get_all_referrers(account_id, page=0):
    if not isObject(account_id):
        account_id = _account_id(account_id)

    con = psycopg2.connect(**config.POSTGRES)
    cur = con.cursor()

    offset = int(page) * 20;

    query = "select * from referrers where referrer=%s ORDER BY rid DESC LIMIT 20 OFFSET %s"
    cur.execute(query, (account_id,str(offset), ))
    results = cur.fetchall()

    return results

def get_grouped_limit_orders(quote, base, group=10, limit=False):
    if not limit:
        limit = 10
    elif int(limit) > 50:
        limit = 50

    if not isObject(base):
        base_asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[base],  0])[0]
        base = base_asset['id']
    if not isObject(quote):
        quote_asset = bitshares_ws_client.request('database', 'lookup_asset_symbols', [[quote],  0])[0]
        quote = base_asset['id']

    grouped_limit_orders = bitshares_ws_client.request('orders', 'get_grouped_limit_orders', [base, quote, group, None, limit])

    return grouped_limit_orders