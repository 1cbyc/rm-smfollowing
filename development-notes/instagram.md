one of my first discovery doing this is that instagram returns html instead of json when trying to transmit data.weird but that leaves us with a large chunk of data to manipulate.

	well, it's not all html, there are some json data in the html, so we need to extract the json data from the html. 

i also noticed the instagram api is rejecting login payload and returning html instead of json so extracting the html response to see if the ip is blocked or if there is a verification challenge is what i got going rn.

figured there is a challenge checkpoint actualy...like a captcha screen, so will work it out and fix any prompt manually for now.like "this was me" prompt.

	atp, i decided t use cookies instead of password.

i won't tell you how i got the cookies, but i got them. becausse if you don't know how to get session id of your cookieStore, then you have no business doing this.YOU ARE A CIVILLAIN!

okay, i figured out why IG_SESSIONID wasn't immediately fixing the problem!

so, because instagrapi acts like the official Instagram Android App.Every time the script runs without an existing session, it generates a completely random "Android Device ID" to pretend to be a mobile phone.and when i dumped my IG_SESSIONID cookie from a web browser into the API, instagram's system saw a web cookie suddenly teleport to a brand new Android phone, so they instantly threw up the Challenge Checkpoint again. And because the script crashed, it never saved the newly generated Android Device ID, meaning every single time i ran the script, it looked like a completely different phone!

what i did now is that i refactored the script to fix this loop, and it now strictly generates and saves my Android Device ID(session.json) before even attempting to contact Instagram.so the android device id is now permanent.so even if instagram blocks stuff, you will just use that method of approving on yoour phone to fix ImageTrack.

like just pen the instagram app on your real phone, and you should see a prompt saying "Suspicious Login Attempt" for a new android device.Click "This was me".once you've approved the specific device ID you created, just run the script again.

i think i would just use web app user agent string everywhere to prevent any user mismatch isSecureContext. and also i added a way to stabilize the android identity hash using the username before cl.int()

changed my mind entirely about using session id. dont want to make thing cmplciated for the average user.

yesterday, i changed my view and i started messing with another instagram unfollow bot idea. honestly didn’t think it would stress me like this, but here we are. the first thing i thought was just scrape the access tool, but instagram turned out to be doing rubbish with that endpoint. it only shows recent activity, not the real full list. so obviously the results came out very funny. like it was saying people aren’t following me back when i literally know they do. so that part was dead on arrival.

then chrome headless decided to embarrass me. login kept breaking. apparently instagram’s login page doesn’t like headless browsers anymore. headless selenium + ig = instant wahala. i got some rust/driver crash nonsense. annoying. i had to switch to visible chrome before login. feels weird watching a bot log me in, but it works.

thought about scraping from the real profile instead the modal that shows up when you click followers or following. that’s the stable method. everybody online pretends like the access tool works but it’s pure scam. the real modal loads all accounts if you scroll enough. so that’s what i’m switching to.

the scrolling itself is another madness. instagram loads like 12 items at a time. if i’m not careful, it will stop loading halfway and the bot will think it’s done. i need to add retries or scroll checks. this is why coding bots for ig is not let me just code small thing. it’s more like let me wrestle javascript and 100 anti-bot layers.

also added the human-like behavior so they don’t ban my account. random delays, small scroll steps, no rushing. instagram is paranoid these days. everything suspicious gets rate-limited. i even had to add auto pause because if ig says try again later, i can’t just be stubborn. better to just chill small.

funny enough, the whitelist idea is actually very useful. i don’t want the bot unfollowing people i know personally or my wife (god forbid). so whitelist is a must.

still feels surreal watching code move my mouse and unfollow people one by one. very “i built this thing with my hands” moment.

overall, this bot is getting cleaner and safer. feels like i’m building a small product instead of a script. which is interesting.

okay, so i got things right and working finally. from getting the followign list to getting to save them to file in caase i wqnt to check those accounts again. also, i did it to be going strong at about 10 per minute. 

i did this:
```bash
.venv/bin/python unfollow.py --yes > /tmp/uf.log 2>&1 &
echo "PID: $!"
```

so i could load the PID from created earlier, so things don't break. i also added a --yes flag to skip any prompt cleanly, then run it as a proper foreground process.

one good thing about this whole stuff is that once you run it, i did it in such a way that you'd get all the details of a user like this (in your data/following.json file):

```json

  {
    "strong_id__": "113XXXXXX42",
    "pk": "113XXXXXX42",
    "pk_id": "113XXXXXX42",
    "id": "113XXXXXX42",
    "full_name": "dr. jay",
    "fbid_v2": "17841411479270286",
    "third_party_downloads_enabled": 1,
    "profile_pic_id": "3800864974546167211_113XXXXXX42",
    "profile_pic_url": "https://instagram.fabv7-1.fna.fbcdn.net/v/t51.2885-19/610688973_18170397904382643_8298519481802601224_n.jpg?stp=dst-jpg_s150x150_tt6&efg=eyJ2ZW5jb2RlX3RhZyI6InByb2ZpbGVfcGljLmRqYW5nby44NjcuYzIifQ&_nc_ht=instagram.fabv7-1.fna.fbcdn.net&_nc_cat=103&_nc_oc=Q6cZ2QFJVNcPQxlVrkcvpFEEP9idECyQ68mRY8NI-K0oNcboAlBOoy_89LyvBtYjWzBn8cg&_nc_ohc=nBrx45XSTFcQ7kNvwHFuowf&_nc_gid=3Tif9dy6DPBmiGSmol5PUQ&edm=ALB854YBAAAA&ccb=7-5&oh=00_AfsE1wbwuE3iXWXhLtSbeHvSoKAQaJXiljUsVLlF0ZdJhQ&oe=69A3C73E&_nc_sid=ce9561",
    "is_verified": false,
    "username": "graceb.oi",
    "is_private": true,
    "has_anonymous_profile_picture": false,
    "account_badges": [],
    "latest_reel_media": 0,
    "is_favorite": false
  },
  {
    "strong_id__": "32XXXX7113",
    "pk": "32XXXX7113",
    "pk_id": "32XXXX7113",
    "id": "32XXXX7113",
    "full_name": "Adeola",
    "fbid_v2": "17841403213408978",
    "third_party_downloads_enabled": 1,
    "profile_pic_id": "3319217530129839473_32XXXX7113",
    "profile_pic_url": "https://instagram.fabv7-1.fna.fbcdn.net/v/t51.2885-19/431247750_1403496616967762_9138244564723539865_n.jpg?stp=dst-jpg_s150x150_tt6&efg=eyJ2ZW5jb2RlX3RhZyI6InByb2ZpbGVfcGljLmRqYW5nby4xMDgwLmMyIn0&_nc_ht=instagram.fabv7-1.fna.fbcdn.net&_nc_cat=102&_nc_oc=Q6cZ2QFJVNcPQxlVrkcvpFEEP9idECyQ68mRY8NI-K0oNcboAlBOoy_89LyvBtYjWzBn8cg&_nc_ohc=SYjIm17x5X4Q7kNvwHZnPZ9&_nc_gid=3Tif9dy6DPBmiGSmol5PUQ&edm=ALB854YBAAAA&ccb=7-5&oh=00_AfsSOJ8bhsfeBQJqqZq1prjEJ2bndP9qZD4nJ2mJhzsHTg&oe=69A3AFE2&_nc_sid=ce9561",
    "is_verified": false,
    "username": "_deolaaa_",
    "is_private": false,
    "has_anonymous_profile_picture": false,
    "account_badges": [],
    "latest_reel_media": 0,
    "is_favorite": false
  },
``