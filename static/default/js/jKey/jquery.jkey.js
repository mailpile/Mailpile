/*
	Copyright (c) 2011 Oscar Godson ( http://oscargodson.com ) and Sebastian Nitu ( http://sebnitu.com )
	
	Permission is hereby granted, free of charge, to any person obtaining a copy
	of this software and associated documentation files (the "Software"), to deal
	in the Software without restriction, including without limitation the rights
	to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
	copies of the Software, and to permit persons to whom the Software is
	furnished to do so, subject to the following conditions:
	
	The above copyright notice and this permission notice shall be included in
	all copies or substantial portions of the Software.
	
	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
	THE SOFTWARE.
	
	More infomation on http://oscargodson.com/labs/jkey
	or fork it at https://github.com/OscarGodson/jKey
	
	Special thanks to Macy Abbey
*/
(function($) {
	$.fn.jkey = function(keyCombo,options,callback) {

  //Check if the selected element was the window and make it document
  //We do this because IE will fail if you select window since you can't attach
  //keypresses to the window in IE
  var $this = this;
  if(this[0] && !this[0].parentNode){ $this = document; }

		// Save the key codes to JSON object
		var keyCodes = { 
    /* start the a-z keys */
    'a' : 65,
    'b' : 66,
    'c' : 67,
    'd' : 68,
    'e' : 69,
    'f' : 70,
    'g' : 71,
    'h' : 72,
    'i' : 73,
    'j' : 74,
    'k' : 75,
    'l' : 76,
    'm' : 77,
    'n' : 78,
    'o' : 79,
    'p' : 80,
    'q' : 81,
    'r' : 82,
    's' : 83,
    't' : 84,
    'u' : 85,
    'v' : 86,
    'w' : 87,
    'x' : 88,
    'y' : 89,
    'z' : 90,
    /* start number keys */
    '0' : 48,
    '1' : 49,
    '2' : 50,
    '3' : 51,
    '4' : 52,
    '5' : 53,
    '6' : 54,
    '7' : 55,
    '8' : 56,
    '9' : 57,
    /* start the f keys */
    'f1' : 112,
    'f2' : 113,
    'f3' : 114,
    'f4' : 115,
    'f5' : 116,
    'f6' : 117,
    'f7' : 118,
    'f8' : 119,
    'f9' : 120,
    'f10': 121,
    'f11': 122,
    'f12': 123,
    /* start the modifier keys */
    'shift' : 16,
    'ctrl' : 17,
    'control' : 17,
    'alt' : 18,
    'option' : 18, //Mac OS key
    'opt' : 18, //Mac OS key
    'cmd' : 224, //Mac OS key
    'command' : 224, //Mac OS key
    'fn' : 255, //tested on Lenovo ThinkPad
    'function' : 255, //tested on Lenovo ThinkPad
    /* Misc. Keys */
    'backspace' : 8,
    'osxdelete' : 8, //Mac OS version of backspace
    'enter' : 13,
    'return' : 13, //Mac OS version of "enter"
    'space':32,
    'spacebar':32,
    'esc':27,
    'escape':27,
    'tab':9,
    'capslock':20,
    'capslk':20,
    'super':91,
    'windows':91,
    'insert':45,
    'delete':46, //NOT THE OS X DELETE KEY!
    'home':36,
    'end':35,
    'pgup':33,
    'pageup':33,
    'pgdn':34,
    'pagedown':34,
    /* Arrow keys */
    'left' : 37,
    'up'   : 38,
    'right': 39,
    'down' : 40,
    /* Special char keys */
    '!':49,
    '@':50,
    '#':51,
    '$':52,
    '%':53,
    '^':54,
    '&':55,
    '*':56,
    '(':57,
    ')':48,
    '`':96,
    '~':96,
    '-':45,
    '_':45,
    '=':187,
    '+':187,
    '[':219,
    '{':219,
    ']':221,
    '}':221,
    '\\':220, //it's actually a \ but there's two to escape the original
    '|':220,
    ';':59,
    ':':59,
    "'":222,
    '"':222,
    ',':188,
    '<':188,
    '.':190,
    '>':190,
    '/':191,
    '?':191
		};

		var x = '';
		var y = '';
		if(typeof options == 'function' && typeof callback == 'undefined'){
			callback = options;
			options = false;
		}

		//IE has issues here... so, we "convert" toString() :(
		if(keyCombo.toString().indexOf(',') > -1){ //If multiple keys are selected
			var keySplit = keyCombo.match(/[a-zA-Z0-9]+/gi);
		}
		else { //Else just store this single key
			var keySplit = [keyCombo];
		}
		for(x in keySplit){ //For each key in the array...
			if(!keySplit.hasOwnProperty(x)) { continue; }
			//Same as above for the toString() and IE
			if(keySplit[x].toString().indexOf('+') > -1){
				//Key selection by user is a key combo
				// Create a combo array and split the key combo
				var combo = [];
				var comboSplit = keySplit[x].split('+');
				// Save the key codes for each element in the key combo
				for(y in comboSplit){
					combo[y] = keyCodes[ comboSplit[y] ];
				}
				keySplit[x] = combo;
			}
			else {
				//Otherwise, it's just a normal, single key command
				keySplit[x] = keyCodes[ keySplit[x] ];
			}
		}
			
		function swapJsonKeyValues(input) {
			var one, output = {};
			for (one in input) {
				if (input.hasOwnProperty(one)) {
					output[input[one]] = one;
				}
			}
			return output;
		}
			
		var keyCodesSwitch = swapJsonKeyValues(keyCodes);
			
		return this.each(function() {
			$this = $(this);
			
			// Create active keys array
			// This array will store all the keys that are currently being pressed
			var activeKeys = [];
			$this.bind('keydown.jkey',function(e){
			// Save the current key press
			activeKeys[ e.keyCode ] = e.keyCode;
	
			if($.inArray(e.keyCode, keySplit) > -1){ // If the key the user pressed is matched with any key the developer set a key code with...
				if(typeof callback == 'function'){ //and they provided a callback function
					callback.call(this, keyCodesSwitch[e.keyCode] ); //trigger call back and...
					if(options === false){
						e.preventDefault(); //cancel the normal
					}
				}
			}
			else { // Else, the key did  not match which means it's either a key combo or just dosn't exist
				// Check if the individual items in the key combo match what was pressed
				for(x in keySplit){
					if($.inArray(e.keyCode, keySplit[x]) > -1){
						// Initiate the active variable
						var active = 'unchecked';
						
						// All the individual keys in the combo with the keys that are currently being pressed
						for(y in keySplit[x]) {
							if(active != false) {
								if($.inArray(keySplit[x][y], activeKeys) > -1){
									active = true;
								}
								else {
									active = false;
								}
							}
						}
						// If all the keys in the combo are being pressed, active will equal true
						if(active === true){
							if(typeof callback == 'function'){ //and they provided a callback function
								
								var activeString = '';
								
								for(var z in activeKeys) {
									if (activeKeys[z] != '') {
										activeString += keyCodesSwitch[ activeKeys[z] ] + '+';
									}
								}
								activeString = activeString.substring(0, activeString.length - 1);
								callback.call(this, activeString ); //trigger call back and...
								if(options === false){
									e.preventDefault(); //cancel the normal
								}
							}
						}
					}
				}
			} // end of if in array
			}).bind('keyup.jkey',function(e) {
				// Remove the current key press
				activeKeys[ e.keyCode ] = '';
			});
		});
	}
})(jQuery);