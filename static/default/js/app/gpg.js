MailPile.prototype.gpgrecvkey = function(keyid) {
	console.log("Fetching GPG key 0x" + keyid);
	mailpile.json_get("gpg recv_key", {}, function(data) {
		console.log("Fetch command execed for GPG key 0x" + keyid + ", resulting in:");
		console.log(data);
	});
}

MailPile.prototype.gpglistkeys = function() {
	mailpile.json_get("gpg list", {}, function(data) {
		$("#content").append('<div class="dialog" id="gpgkeylist"></div>');
		for (k in data.results) {
			key = data.results[k]
			$("#gpgkeylist").append("<li>Key: " + key.uids[0].replace("<", "&lt;").replace(">", "&gt;") + ": " + key.pub.keyid + "</li>");
		}
	});
}