/* Mailpile - Helpers
   - a collection of random functions and things
*/

String.prototype.startsWith = function(str) {
  return this.indexOf(str) === 0;
};


String.prototype.contains = function(it) { 
  return this.indexOf(it) !== -1;
};


Number.prototype.pad = function(size) {
	// Unfortunate padding function....
	if (typeof(size) !== "number") {
    size = 2;
  }
	var s = String(this);
	while (s.length < size) { s = "0" + s; }
	return s;
};


/* Abbreviates Numbers */
function abbrNum(number, decPlaces) {

  // 2 decimal places => 100, 3 => 1000, etc
  decPlaces = Math.pow(10,decPlaces);

  // Enumerate number abbreviations
  var abbrev = [ "k", "m", "b", "t" ];

  // Go through the array backwards, so we do the largest first
  for (var i = abbrev.length-1; i >= 0; i--) {

    // Convert array index to "1000", "1000000", etc
    var size = Math.pow(10,(i+1)*3);

    // If the number is bigger or equal do the abbreviation
    if (size <= number) {
      // Here, we multiply by decPlaces, round, and then divide by decPlaces.
      // This gives us nice rounding to a particular decimal place.
      number = Math.round(number*decPlaces/size)/decPlaces;
      
      // Handle special case where we round up to the next abbreviation
      if((number === 1000) && (i < abbrev.length - 1)) {
        number = 1;
        i++;
      }
      
      // Add the letter for the abbreviation
      number += abbrev[i];
      
      // We are done... stop
      break;
    }
  }

  return number;
}


$.fn.serializeObject = function() {

  var o = {};
  var a = this.serializeArray();

  $.each(a, function() {
    if (o[this.name] !== undefined) {
      if (!o[this.name].push) {
        o[this.name] = [o[this.name]];
      }
      o[this.name].push(this.value || '');
    } else {
      o[this.name] = this.value || '';
    }
  });

  return o;
};