
var Page = function(binddom) {
	this.dom_object = binddom;
	this.buttons = {};
	this.show_actions = [];
	this.hide_actions = [];
	this.input_validators = {};
	this.parent = null;
};


Page.prototype.bind_button = function(btn, callback) {
	this.buttons[btn] = callback;
	return this;
}

Page.prototype.bind_show = function(callback) {
	this.show_actions.push(callback);
}

Page.prototype.bind_hide = function(callback) {
	this.hide_actions.push(callback);
}

Page.prototype.bind_validator = function(dom, callback) {
	if (this.input_validators[dom] == undefined) {
		this.input_validators[dom] = [];
	}
	this.input_validators[dom].push(callback);
}

Page.prototype.init = function(parent) {
	console.log("Intializing page!");
	if (parent) {
		this.parent = parent;
		console.log("Set page parent to ", parent);
	}

	return true;
}

Page.prototype.route = function(routename) {
	this.route = routename;
	return this;
}

Page.prototype.show = function() {
	for (i in this.show_actions) {
		this.show_actions[i](this);
	}
	for (btn in this.buttons) {
		$(btn).click(this.buttons[btn]);
	}
	$(this.dom_object).show();
};

Page.prototype.hide = function() {
	for (i in this.hide_actions) {
		this.hide_actions[i](this);
	}
	for (v in this.input_validators) {
		if (!this.input_validators[v]($(v))) {
			// Mailpile.UI.InputError($(v));
			break;
		}
	}
	$(this.dom_object).hide();
};

Page.prototype.next = function() {
	if (this.parent) {
		this.parent.next();
	} else {
		console.log("Parent:", this.parent);
	}
	return this;
};

Page.prototype.prev = function() {
	if (this.parent) {
		this.parent.prev();
	} else {
		console.log("Parent:", this.parent);
	}
	return this;
};
