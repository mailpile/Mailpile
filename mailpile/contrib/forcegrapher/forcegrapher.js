/* Use The Force, Grapher
    - Renders your current search result set as a force directed graph
    - Built using D3
*/

return {
    draw: function(graph) {

        // Determine & Set Height
        var available_height = $(window).height() - ($('#header').height() + $('.sub-navigation').height());
        var available_width = $("#content-wide").width();

        $('#pile-graph-canvas').height(available_height);
        $('#pile-graph-canvas').width(available_width);
        $("#pile-graph-canvas-svg").attr('height', available_height).height(available_height);

        var width = available_width;
        var height = available_height;
        var force = d3.layout.force()
                    .charge(-300)
                    .linkDistance(100)
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
            .style("stroke", "#333333")
            .style("stroke-width", '1px');

        // Calculate # of connections
        // function(d) { return Math.sqrt(3*d.value); }

        var node = svg.selectAll(".node")
              .data(graph.nodes)
              .enter().append("g")
              .attr("class", "node")
              .call(force.drag);

        node.append("circle")
            .attr("r", 8)
            .style("fill", function(d) { return color("#337FB2"); })

        node.append("text")
            .attr("x", 12)
            .attr("dy", "0.35em")
            .style({"opacity": "0.3", "font-size": "12px"})
            .text(function(d) {
              if (d.name !== undefined) {
                return d.name;
              } else {
                var email_name = d.email.split('@');
                return email_name[0];
              }
            });

        link.append("text").attr("x", 12).attr("dy", ".35em").text(function(d) { return d.type; })

        node.on("click", function(d, m, q) {

            // d.attr("toggled", !d.attr("toggled"));
            // d.style("color", "#f00");
            if (Mailpile.graphselected.indexOf(d["email"]) < 0) {
                d3.select(node[q][m]).selectAll("circle").style("fill", "#4B9441");
                Mailpile.graphselected.push(d["email"]);
            } else {
                Mailpile.graphselected.pop(d["email"]);
                d3.select(node[q][m]).selectAll("circle").style("fill", "#337FB2");
            }
            Mailpile.graph_actionbuttons();
        });
        node.on("mouseover", function(d, m, q) {
            d3.select(node[q][m]).selectAll("text").style("opacity", "1");
        });
        node.on("mouseout", function(d, m, q) {
            d3.select(node[q][m]).selectAll("text").style("opacity", "0.2");
        });

        force.on("tick", function() {
            node.attr("transform", function(d) {
                if (d.x < 0) { d.x = 0; }
                if (d.y < 0) { d.y = 0; }
                if (d.x > width) { d.x = width; }
                if (d.y > height) { d.y = height; }
                return "translate(" + d.x + "," + d.y + ")";
            });
            link.attr("x1", function(d) { return d.source.x; })
                .attr("y1", function(d) { return d.source.y; })
                .attr("x2", function(d) { return d.target.x; })
                .attr("y2", function(d) { return d.target.y; });
        });
    }
}
