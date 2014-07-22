/* Wizard - Setup */
var Wizard = function(container, titlecontainer) {
  this.container = container;
  this.titlecontainer = titlecontainer;
  this.curpage = 0;
  this.pages = [];
  this.initialized = false;
};


Wizard.prototype.init = function() {
  console.log("Initializing Wizard!");
  if (this.initialized) { return false; }
  for (page in this.pages) {
    this.pages[page].init(this);
  }
  this.initialized = true;
  return true;
};


Wizard.prototype.set_title = function(title) {
  $(this.titlecontainer).html(title);
};


Wizard.prototype.goto = function(page) {
  if (page % 1 != 0) {
    // page is not an integer
    for (i in this.pages) {
      if (this.pages[i].route == page) {
        page = i;
      }
    }
  }

  if (this.pages.length <= page || page < 0) {
    return false;
  }
  this.pages[this.curpage].hide();
  this.curpage = page;
  this.pages[this.curpage].show();
  return this.pages[this.curpage];
};


Wizard.prototype.go = function() {
  this.init();
  return this.goto(0);
};


Wizard.prototype.show = function() {
  this.go();
};


Wizard.prototype.hide = function() {
  this.pages[this.curpage].hide();
};


Wizard.prototype.next = function() {
  return this.goto(this.curpage+1);
}


Wizard.prototype.prev = function() {
  return this.goto(this.curpage-1);
}
