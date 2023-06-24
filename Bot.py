# bot.py
import os
import io
import logging
import asyncio
from dotenv import load_dotenv
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import pandas as pd
import yfinance as yf
import discord
from discord import ActionRow, Button, ButtonStyle
from millify import millify
from millify import prettify
from forex_python.converter import CurrencyCodes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
#the token of your discord bot
TOKEN = os.environ.get("BOT_KEY")
#the channel id of the channel you wish to store the generated images in, the images there will be used for the embed
ImageChannel = os.environ.get("IMAGE_CHANNEL_ID")
#the config data for the message components buttons. for the options first set a period and then the interval seperated by a _
options = ['1d_5m','1wk_1h','6mo_1d']
labels = ['Day','Week','6 Months']
prepost = [False,True,False]

bot = discord.Client()
c = CurrencyCodes()

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')

@bot.event
async def on_message(message):
    if not is_command(message): return
    data = message.content.split()
    if data[1] == 'help':
        await message.channel.send("Stonktracker is a bot for tracking stocks. Usage is as follows:\n`!stonk <ticker>`\nYou can also click on the currently selected graph period to refresh the data")
        return

    msg = await message.channel.send(f'Gettings stonk data for {data[1]}')
    channel = await bot.fetch_channel(ImageChannel)
    cache = ['','','']
    previous = ''
    button_id = options[0]

    #message components interaction loop
    while True:
        button_index = options.index(button_id)
        #gets new data if the button is pressed again or if it hasn't been accessed before
        if not cache[button_index] or previous == button_id:
            if button_id == options[0]:
                try: stock = get_stockData(yf.Ticker(data[1]))
                except Exception as e:
                    logger.exception(e)
                    await msg.edit(content = f"Could not get data for {data[1]}, check your fucking spelling")
                    return
                embed = generate_embed(stock,data[1])

            param = button_id.split('_')
            graph = get_graph(yf.download(tickers=data[1],period=param[0],interval=param[1],rounding=True, auto_adjust=True, prepost=prepost[button_index]),stock.name)
            file = await channel.send(file=graph)
            await asyncio.sleep(1)
            cache[button_index] = file.attachments[0].url

        embed.set_image(url = cache[button_index])
        await msg.edit(content = '', embed = embed , components = generate_components(button_index))
        previous = button_id

        def _check(i: discord.Interaction, b):
            return i.message == msg

        interaction, button = await bot.wait_for('button_click',check=_check)
        button_id = button.custom_id
        # This sends the Discord-API that the interaction has been received and is being "processed"
        await interaction.defer()

def roundby2(number):
    return round(float(number),2)

def get_change(current, previous):
    if current == previous: return 100.0
    try: return float(current - previous) / abs(previous) * 100
    except ZeroDivisionError: return 0

def get_stockData(ticker):
    stockData = StockData()
    try:
        data = ticker.history(period='1h')
        info = ticker.info
        fast_info = ticker.fast_info
        last_quote = (data.tail(1)['Close'].iloc[0])
    except:
        raise NameError('no data')

    stockData.name = get_data_with_fallback(info, "shortName","")
    stockData.value = prettify(roundby2(last_quote))
    stockData.dif = roundby2(get_change(last_quote,get_data_with_fallback(fast_info,"previous_close",0)))
    stockData.high = prettify(roundby2(get_data_with_fallback(fast_info,"year_high",0)))
    stockData.low = prettify(roundby2(get_data_with_fallback(fast_info, "year_low", 0)))
    stockData.cap = millify(get_data_with_fallback(fast_info ,'market_cap', 0), precision=2, drop_nulls=False)
    stockData.profits = millify(get_data_with_fallback(info,"grossProfits", '0'), precision=2, drop_nulls=False)
    stockData.currency = get_data_with_fallback(fast_info,'currency','')
    stockData.logo = get_data_with_fallback(fast_info ,'logo_url', '')
    return stockData

def get_graph(data,name):
    df = pd.DataFrame(data)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=('OHLC', 'Volume'), row_width=[0.2, 0.7])
    fig.add_trace(go.Candlestick(x=df.index, open=df.Open, high=df.High,low=df.Low,close=df.Close,name=''),row=1,col=1)
    fig.add_trace(go.Bar(x=df.index, y=df.Volume, marker_color='lightblue',marker_line_color='blue',marker_line_width=1.5,opacity=0.7),row=2,col=1)
    fig.add_annotation(showarrow=True,x=df.High.idxmax(),y=df.High.max(),text=df.High.max(),opacity=0.7)
    fig.add_annotation(showarrow=True,x=df.Low.idxmin(),y=df.Low.min(),ay = 30,text=df.Low.min(),opacity=0.7)
    fig.update_layout(title = name, xaxis_rangeslider_visible=False, showlegend = False)
    fig.update_layout(title_font_size=40, font_size=25)
    return discord.File(io.BytesIO(fig.to_image(format="jpg", width = 1280, height = 720)), filename="chart.jpg")

def get_data_with_fallback(tickerInfo, parameter, fallback):
    try:
        data = tickerInfo[parameter]
    except:
        print(f"error getting {parameter}")
        data = fallback
    return data

def generate_embed(stock, name):
    if stock.dif >= 0: color = discord.Color.green()
    else: color = discord.Color.red()

    if stock.currency:
        symbol =c.get_symbol(stock.currency)
        symbol = symbol[len(symbol)-1]
    else: symbol =''

    if stock.profits == '0.00': stock.profits ='N/A'
    else: stock.profits = symbol + stock.profits

    embed=discord.Embed(title=stock.name, url=f"https://finance.yahoo.com/quote/{name}", color=color)
    embed.set_thumbnail(url=stock.logo)
    embed.add_field(name="Value", value=symbol+stock.value, inline=True)
    embed.add_field(name="52W high", value=symbol+stock.high, inline=True)
    embed.add_field(name="Profits", value=stock.profits, inline=True)
    embed.add_field(name="Difference", value=f"{stock.dif}%", inline=True)
    embed.add_field(name="52W low", value=symbol+stock.low, inline=True)
    embed.add_field(name="Market Cap", value=symbol+stock.cap, inline=True)
    return embed

def is_command(message):
    if message.author == bot.user: return False
    if not message.content: return False
    if message.content[0] != '!': return False
    data = message.content.split()
    if len(data) == 1: return False
    if data[0] != '!stonk' and data[0] != '!stonks': return False
    return True

def generate_components(highlight_index):
    if len(labels) <= 1: return []
    actionrow = ActionRow()
    for i in range(len(labels)):
        if i == highlight_index:
            actionrow.add_component(Button(label=labels[i],custom_id=options[i],style=ButtonStyle.blurple))
        else:
            actionrow.add_component(Button(label=labels[i],custom_id=options[i]))
    return [actionrow]

class StockData:
    def __init__(self):
        self.name = ''
        self.value = '0'
        self.dif = 0
        self.high = '0'
        self.low = '0'
        self.profits = '0'
        self.cap = '0'
        self.currency = ''
        self.logo = ''

bot.run(TOKEN)
