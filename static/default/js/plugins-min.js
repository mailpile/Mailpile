// STATICALLY DECLARED PLUGINS - TOTAL HACK RIGHT NOW SO I CAN JUST WORK ON SPECING THINGS OUT
// I THINK THIS SHOULD BE INJECTED VIA PYTHON or FROM AN API ENDPOINT
var plugins_hack = ["force-grapher","maildeck"];


/* Load Plugins - THIS SHOULD ALSO JUST BE INJECTED BY PYTHON METHINKS */
$.each(plugins_hack, function(key, plugin){

  var params = '';

  $.getJSON('/static/plugins/' + plugin + '/config.json', params, function(result) {

    // Add To Config
    mailpile.plugins.push(result);
    
    var view_index = _.indexOf(result.views, mailpile.instance.command);

    if (view_index > -1) {
      $.ajax({
		    url			 : '/static/plugins/' + plugin + '/' + result.views[view_index] + '.html',
		    type		 : 'GET',
		    dataType : 'html',
	      success  : function(response) {
          $('body').append(response);
	      }
	    });   
    }
    
  });

});

/* **********************************************
     Begin force-grapher.js
********************************************** */

/* Use The Force, Grapher
    - Renders your inbox as a force directed graph
    - Built using D3
*/

MailPile.prototype.results_graph = function() {

  // Change Navigation 
	$('#btn-display-graph').addClass('navigation-on');
	$('#btn-display-list').removeClass('navigation-on');

	// Show & Hide Pile View
	$('#pile-results').hide('fast', function() {

	  $('#form-pile-results').hide('fast');
    $('.pile-speed').hide('fast');
    $('#footer').hide('fast');
    $('#sidebar').hide('fast');

	  $('#pile-graph').hide().delay(1000).show();
	});

  // Determine & Set Height
  var available_height = $(window).height() - ($('#header').height() + $('.sub-navigation').height());

  $('#pile-graph-canvas').height(available_height);
  $("#pile-graph-canvas-svg").attr('height', available_height).height(available_height);

  // Load Network Data
	d3.json("/api/0/shownetwork/?q=" + mailpile.instance.search_terms, function(graph) {
		graph = graph.result;
		console.log(graph);
    
    console.log(available_height);
    				
		var width = 640; // $("#pile-graph-canvas").width();
		var height = available_height;
		var force = d3.layout.force()
	   				.charge(-300)
	   				.linkDistance(75)
	   				.size([width, height]);

		var svg = d3.select("#pile-graph-canvas-svg");
		$("#pile-graph-canvas-svg").empty();

		var color = d3.scale.category20();

		var tooltip = d3.select("body")
		    .append("div")
	    	.style("position", "absolute")
	    	.style("z-index", "10")
	    	.style("visibility", "hidden")
	    	.text("a simple tooltip");

		force
			.nodes(graph.nodes)
	    	.links(graph.links)
	    	.start();

		var link = svg.selectAll(".link")
			.data(graph.links)
			.enter().append("line")
			.attr("class", "link")
			.style("stroke-width", function(d) { return Math.sqrt(3*d.value); });

		var node = svg.selectAll(".node")
		      .data(graph.nodes)
			  .enter().append("g")
		      .attr("class", "node")
		      .call(force.drag);

		node.append("circle")
			.attr("r", 8)
		    .style("fill", function(d) { return color("#3a6b8c"); })

	    node.append("text")
	    	.attr("x", 12)
	    	.attr("dy", "0.35em")
	    	.style("opacity", "0.3")
	    	.text(function(d) { return d.email; });

	    link.append("text").attr("x", 12).attr("dy", ".35em").text(function(d) { return d.type; })

	   	node.on("click", function(d, m, q) {
	   		// d.attr("toggled", !d.attr("toggled"));
	   		// d.style("color", "#f00");
	   		if (mailpile.graphselected.indexOf(d["email"]) < 0) {
		   		d3.select(node[q][m]).selectAll("circle").style("fill", "#4b7945");
		   		mailpile.graphselected.push(d["email"]);
	   		} else {
	   			mailpile.graphselected.pop(d["email"]);
	   			d3.select(node[q][m]).selectAll("circle").style("fill", "#3a6b8c");
	   		}
	   		mailpile.graph_actionbuttons();
	   	});
		node.on("mouseover", function(d, m, q) {
			d3.select(node[q][m]).selectAll("text").style("opacity", "1");
		});
		node.on("mouseout", function(d, m, q) {
			d3.select(node[q][m]).selectAll("text").style("opacity", "0.3");
		});

		force.on("tick", function() {
			link.attr("x1", function(d) { return d.source.x; })
			    .attr("y1", function(d) { return d.source.y; })
			    .attr("x2", function(d) { return d.target.x; })
			    .attr("y2", function(d) { return d.target.y; });

			node.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });
		});
	});

}
