/* Use The Force, Grapher
    - Renders your current search result set as a force directed graph
    - Built using D3
*/

return {
    draw: function(graph) {
        // Determine & Set Height
        var available_height = $(window).height() - ($('#header').height() + $('.sub-navigation').height());
        var available_width = $("#content-view").width();

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
            .style("stroke", "#000")
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
