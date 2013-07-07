# jKey Beta 1.1

## Key shortcuts made simple

Visit [http://oscargodson.github.com/jKey/](http://oscargodson.github.com/jKey/) for a live demo

### Examples

#### Example 1 - Basic Usage

Below is the most basic usage. Press the a key to give you an alert. Code below:

    $(document).jkey('a',function(){
    	jkey.log('You pressed the a key.');
    });

##### Example 1A - Selecting An Element

jKey works with jQuery, so you can select any applicable element to set a key command to. Basically, any element that can be focused on such as an input or textarea can have a key command applied to it. Example: 

    $('input').jkey('i',function(){
    	jkey.log('You pressed the i key inside of an input.');
    });

##### Example 1B - Comboing Anything!

Unlike OS key shortcuts, jKey allows you to combo just about any key supported by jKey. For example:

    $(document).jkey('y+u',function(){
    	jkey.log('You pressed y and u!');
    });

Please see the key support section below to see what's supported by jKey.

#### Example 2 - Key Combos

    $(document).jkey('alt+d',function(){
    	jkey.log('Congrats, you did a key combo: alt+d');
    });

##### Example 2A - Chaining Key Combos

With jKey you can intuitively connect more than just two keys for a combo. For example:

    $(document).jkey('alt+shift+s',function(){
    	jkey.log('Congrats, you did a key combo: alt+shift+s');
    });

#### Example 3 - Multiple Selections

You can also do multiple selections. You can select multiple keys just as you'd select multiple elements in CSS or jQuery. Useful for trying to catch user intent, e.g. doing w and up, so a user can move a character in a game forward with either key like many computer games.

    $(document).jkey('w, up',function(){
    	jkey.log('You pressed either w, or up!');
    });

#### Example 4 - Grabbing the Keys Pressed in the Callback

Sometimes when working with key shortcuts you want to have similar, but different, events fire when certain keys are pressed. For example, you want to have a sliding animation happen when the user presses up or down. The funcationality is basically the same, speed, animation, tween, AJAX event maybe, etc. However, you're a good developer and you want to keep things [DRY]( http://en.wikipedia.org/wiki/Don't_repeat_yourself). Thanks to jKey this is simple:

    $(document).jkey('left, right',function(key){
    	var direction;
    	if(key == 'left'){
    		direction = 'left';
    	}
    	else{
    		direction = 'right';
    	}
    	jkey.log(direction);
    });
				
				
####Example 5 - Allowing Bubbling of Events
There might be times when you don't want to prevent keys from bubbling such as the up or down keys. By default, jKey will prevent bubbling so that you don't manually have to as *most* of the time when using jKey you don't want it to bubble and make the page go haywire. However, when you do want it to it's just a simple boolean value you set like so:
    
	$('input').jkey('h',true,function(key){
	    jkey.log('Allowed to bubble h!');
    });

#### Key Support

*   a-z
*   0-9
*   f1-f12
*   left, down, up, right
*   esc/escape, insert, delete, home, end, pgup/pageup, pgdn/pagedown, fn/function(3)
*   ctrl/control, alt, shift, backspace/osxdelete(1), enter/return(2), super/windows, capslk/capslock, tab, space/spacebar
*   `, ~, -, _, =, +, [, {, ], }, \, |, ;, :, ', ", ,, <, ., &gt, /, ?

If we're missing something, let us know in the bug reporter on our [Github page](https://github.com/OscarGodson/jKey).

(1) - This is the Mac version of the backspace button. Calling either should work across OSs. Due to conflicts with normal western keyboards, we went with "osxdelete". We suggest just using the backspace.

(2) - This is the Mac version of the enter key. Calling either should work across OSs.

(3) - This will NOT work in Mac OS X. It does not send a key event to the browser. Silly Apple.

#### Important Notes!

##### IE Doesn't Like `$(window)`
This isn't jKey's fault. IE doesn't allow you to attach key events to the window. jKey will try to fix it for you if you do it by accident though. If you want to attach a key event to the document/window use $(document) instead.

##### Don't nest your key commands (for now)

What we mean by this is, as of now, jKey can handle key commands like: alt + a and alt + shift + a in the same document, but when you go to do the 2nd one that includes shift, it'll run the 1st event as well. This is *most likely* not what you want.

##### Special characters that have the share the same physical key, get the same key code

For example, you can call : OR ;, [ OR {, etc. They are the same key to jKey.

##### Function key will NOT work on Mac OS X

There is nothing jKey can do about this. OS X doesn't send a key code back to the browser. Sorry!
