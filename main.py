import praw
import time
import sqlite3 as sq
import configparser
import prawcore.exceptions


config = configparser.ConfigParser()
config.read("config.ini")
subreddit = config.get("SUBREDDIT", "NAME")
moderators = []
command_word = "!strike"
subject_secret = "strike" # this must be the subject in order to strike someone privately by pming the bot


def add_strike(cursor, author, reason, source, connection):
    cursor.execute("""INSERT INTO strikes VALUES (NULL, :reason, :source, (SELECT id FROM users WHERE username=:username))""", {"username": author, "reason": reason, "source": source})
    connection.commit()

def count_amount_of_strikes(cursor, author):
    cursor.execute(
        """SELECT count(strikes.id) AS count From users INNER JOIN strikes on users.id = strikes.user_id WHERE username=:username GROUP BY users.username""",
        {"username": author})  # count the amount of strikes
    return cursor.fetchone()


def gen_strike_table(author, amnt, cursor):
    if amnt >= 3:
        reply_body = f"A strike has been given to u/{author} and it looks like they have exceeded 3 strikes!" \
                     f"\n\nThey have been banned." \
                     f"\n\n Here are their current strikes:" \
                     f"\n\n|Strike No.|Reason|Source|" \
                     f"\n|:-:|:-:|:-:|\n"
    else:
        reply_body = f"A strike has been given to u/{author}!" \
                     f"\n\n Here are their current strikes:" \
                     f"\n\n|Strike No.|Reason|Source|" \
                     f"\n|:-:|:-:|:-:|\n"

    cursor.execute("""SELECT source, reason From users INNER JOIN strikes on users.id = strikes.user_id WHERE username=:username""", {"username": author})
    list_of_sources = cursor.fetchall()

    i = 1
    total_strikes = cursor.execute("""SELECT count(strikes.id) AS count From users INNER JOIN strikes on users.id = strikes.user_id""").fetchone()[0]
    for source, reason in list_of_sources:
        table_row = f"|{i}|{reason}|[Link]({source})|\n"
        reply_body += table_row
        i += 1
    reply_body += f"\n\n***\n\nI am a bot. | Total strikes given to u/{author}: {amnt} | Total strikes given out: {total_strikes}"
    return reply_body

def check_if_user_is_known(cursor, author, connection):
    cursor.execute("""SELECT username FROM users WHERE username=:username""",
                   {"username": author})  # Does this person already exist?
    exist = cursor.fetchone()
    if exist is None:  # if this person does not exist in the database
        cursor.execute("""INSERT INTO users VALUES (NULL, :username)""", {"username": author})  # add this user to DB
        connection.commit()


def process_user(reddit, cursor, author, source, comment_obj):
    global amount_of_strikes
    amount_of_strikes = count_amount_of_strikes(cursor, author)
    if amount_of_strikes:
        amount_of_strikes = amount_of_strikes[0]
    else:
        amount_of_strikes = 1

    if amount_of_strikes >= 3:
        # send mod mail
        try:
            reddit.subreddit(subreddit).message("A user has reached or exceeded 3 strikes!", f"Hello!\n\nA user has reached 3 or more strikes and has been banned!\n\nHere was their final strike: {source}")
            comment_obj.banned.add(author, ban_reason="Exceeded 3 Strikes", ban_message="Automated ban due to exceeding 3 strikes. Contact the moderators if there has been a mistake.", note=f"Their final strike was {source}")
        except Exception as e:
            print(f"ERROR: Couldn't ban user {author}. - {e}")




def scan_comments(reddit, cursor, connection, comment_obj):


    pm_err_msg = f"""Sorry, I didn't understand your message!\n\n
Please make sure you are using the proper syntax and subject!\n\n
Subject must be "strike" (No quotes, Not case sensitive.)\n\n
!strike u/username <reason> <link to rule breaking content>\n\n
Username is not case sensitive. Source URL must contain 'reddit.com'."""

    for comment in comment_obj.stream.comments(skip_existing=True):
        body = comment.body
        initiator = comment.author.name.lower()
        try:
            if command_word in body and initiator in moderators:
                command_comment = comment
                comment = comment.parent()
                author = comment.author.name.lower()
                source = comment.permalink
                raw_reason = body[8:].split(" ")
                reason = " ".join(raw_reason)
                if reason == "":
                    reason = "<None Given>"
                check_if_user_is_known(cursor, author, connection)
                add_strike(cursor, author, reason, source, connection)
                process_user(reddit, cursor, author, source, comment_obj)
                bot_comment = comment.reply(gen_strike_table(author, amount_of_strikes, cursor))
                bot_comment.mod.distinguish(how="yes", sticky=False)
                command_comment.mod.remove()

            for pm in reddit.inbox.unread():
                subject = pm.subject.lower()
                body = pm.body.lower()
                initiator = pm.author.name.lower()
                if not pm.was_comment and initiator in moderators:  # if the bot was PM'd. (Not receive a reply from a comment!)
                    if subject == subject_secret and body[:7] == command_word:
                        raw_author = body[8:].split(" ")[0]
                        author = raw_author.split("/")[-1].lower()
                        raw_reason = body[8:].split(" ")[1:-1]
                        reason = " ".join(raw_reason)
                        raw_source = body.split(" ")[-1:]
                        source = " ".join(raw_source)
                        if len(body.split(" ")) < 4 or reason == "" or "reddit.com" not in body:
                            pm.reply(pm_err_msg)
                            pm.mark_read()
                            break
                        check_if_user_is_known(cursor, author, connection)
                        add_strike(cursor, author, reason, source, connection)
                        process_user(reddit, cursor, author, source, comment_obj)
                        pm.reply(gen_strike_table(author, amount_of_strikes, cursor))
                        pm.mark_read()
                    else:
                        pm.reply(pm_err_msg)
                        pm.mark_read()

        except Exception as e:
            print(f"WARNING: Unknown Error! - {e}")


def initialise():
    try:
        ## Sign into reddit account
        reddit = praw.Reddit(client_id=config.get("ACCOUNT", "CLIENT_ID"),
                             client_secret=config.get("ACCOUNT", "CLIENT_SECRET"),
                             username=config.get("ACCOUNT", "USERNAME"),
                             password=config.get("ACCOUNT", "PASSWORD"),
                             user_agent="3StrikesBot, created by u/ItsTheRedditPolice")
        comment_obj = reddit.subreddit(subreddit)
        user = reddit.user.me()
        print(f"Strike Bot v1.0")
        print(f"-"*30)
        time.sleep(1)
        print(f"Signed in as: {user}")
        print(f"Subreddit: r/{subreddit}\n")
        time.sleep(0.5)

        ## Connect database - will create a new database if one does not exist!
        connection = sq.connect("users.db")
        cursor = connection.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username text not null)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS strikes (id INTEGER PRIMARY KEY, reason text, source text not null, user_id INTEGER, FOREIGN KEY(user_id) REFERENCES users(id))""")
        connection.commit()
        ## Get a list of current moderators
        for mod in reddit.subreddit(subreddit).moderator():
            moderators.append(str(mod).lower())
        print("Bot is now running!")
        ## Grab comments
        scan_comments(reddit, cursor, connection, comment_obj)

    except (prawcore.exceptions.OAuthException, prawcore.exceptions.ResponseException) as e:
        print(f"WARNING: Could not log in to the Reddit account. Make sure the details are correct!\nPress any key to exit.\n\nError: {e}")
        input()
    except Exception as e:
        print(f"ERROR: {e}")
        input()


if __name__ == "__main__":
    initialise()
