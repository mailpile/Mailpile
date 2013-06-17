

function MailPile() {
	this.msgcache = [];
	this.searchcache = [];
}

MailPile.prototype.add = function() {}
MailPile.prototype.attach = function() {}
MailPile.prototype.compose = function() {}
MailPile.prototype.delete = function() {}
MailPile.prototype.extract = function() {}
MailPile.prototype.filter = function() {}
MailPile.prototype.help = function() {}
MailPile.prototype.load = function() {}
MailPile.prototype.mail = function() {}
MailPile.prototype.forward = function() {}
MailPile.prototype.next = function() {}
MailPile.prototype.order = function() {}
MailPile.prototype.optimize = function() {}
MailPile.prototype.previous = function() {}
MailPile.prototype.print = function() {}
MailPile.prototype.reply = function() {}
MailPile.prototype.rescan = function() {}
MailPile.prototype.gpgrecv = function() {}
MailPile.prototype.search = function(q) {
	var that = this;
	this.json_get("search", {"q": q}, function(data) {
		$("#results tbody").empty();
		for (var i = 0; i < data.results.length; i++) {
			tr = $('<tr class="result"></tr>');
			tr.addClass((i%2==0)?"even":"odd");
			tr.append('<td class="checkbox"></td>');
			tr.append('<td class="from">' + data.results[i].msg_info[5] + '</td>');
			tr.append('<td class="subject">' + data.results[i].msg_info[6] + '</td>');
			tr.append('<td class="tags"></td>');
			tr.append('<td class="date"></td>');
			$("#results tbody").append(tr);
		}
		that.chatter(data.chatter);
	});
}
MailPile.prototype.set = function() {}
MailPile.prototype.tag = function() {}
MailPile.prototype.addtag = function() {}
MailPile.prototype.unset = function() {}
MailPile.prototype.update = function() {}
MailPile.prototype.view = function(idx, msgid) {
	var that = this;
	this.json_get("view", {"idx": idx, "msgid": msgid}, function(data) {
		$("#results").empty();
		$that.chatter(data.chatter);
	})
}

MailPile.prototype.json_get = function(cmd, params, callback) {
	var url;
	if (cmd == "view") {
		url = "/=" + params["idx"] + "/" + params["msgid"] + ".json";
	} else {
		url = "/_/" + cmd + ".json";
	}
	$.getJSON(url, params, callback);
}

MailPile.prototype.chatter = function(text) {
	$("#chatter").empty();
	for (var i = 0; i < text.length; i++) {
		$("#chatter").append(text[i] + "\n");
	}
}


var mailpile = new MailPile();

// Non-exposed functions: www, setup
