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

changed my mind entirely about using session id. dont want to make thing cmplciated for the average user