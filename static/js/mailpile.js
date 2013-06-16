

function MailPile() {
	self.msgcache = [];
	self.searchcache = []
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
MailPile.prototype.search = function(q) {}
MailPile.prototype.set = function() {}
MailPile.prototype.tag = function() {}
MailPile.prototype.addtag = function() {}
MailPile.prototype.unset = function() {}
MailPile.prototype.update = function() {}
MailPile.prototype.view = function(msgid) {}

# Non-exposed functions: www, setup