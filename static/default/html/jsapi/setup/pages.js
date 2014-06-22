
var Page = function(template, title) {
    this.template = template;
    this.title = title;
    this.buttons = {};
    this.show_actions = [];
    this.hide_actions = [];
    this.input_validators = {};
    this.parent = null;
    return this;
};

Page.prototype.bind_button = function(btn, callback) {
    this.buttons[btn] = callback;
    return this;
}

Page.prototype.bind_show = function(callback) {
    this.show_actions.push(callback);
    return this;
}

Page.prototype.bind_hide = function(callback) {
    this.hide_actions.push(callback);
    return this;
}

Page.prototype.bind_validator = function(dom, callback) {
    if (this.input_validators[dom] == undefined) {
        this.input_validators[dom] = [];
    }
    this.input_validators[dom].push(callback);
    return this;
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
    var html = $(this.template).html();
    var view = _.template(html);
    this.parent.set_title(this.title);
    $(this.parent.container).html(view);
    for (i in this.show_actions) {
        this.show_actions[i](this);
    }
    for (btn in this.buttons) {
        $(btn).click(this.buttons[btn]);
    }
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
    $(this.parent.container).empty();
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
