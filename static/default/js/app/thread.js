MailPile.prototype.view = function(idx, msgid) {
	this.json_get("view", {"idx": idx, "msgid": msgid}, function(data) {
		if ($("#results").length === 0) {
			$("#content").prepend('<table id="results" class="results"><tbody></tbody></table>');
		}
		$("#results").empty();
	});
};