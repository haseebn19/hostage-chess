/**
 * Hostage Chess: Client-side game logic
 *
 * Handles: chessboard rendering, drag-and-drop with legal move validation,
 * prison/airfield display, drop moves, hostage exchanges, promotion modals,
 * timers, and polling for opponent updates.
 */

/* global Chessboard, GAME_CONFIG, $ */

(function () {
    "use strict";

    // ── State ─────────────────────────────────────────────────────────────

    var cfg = window.GAME_CONFIG;
    var board = null;
    var whiteTime = cfg.whiteTime;
    var blackTime = cfg.blackTime;
    var timerInterval = null;
    var dropMode = false;
    var selectedAirfieldIdx = null;
    var exchangeMode = false;
    var selectedExchange = null;

    // Build a lookup for legal moves keyed by "from" square
    var legalMoveMap = {};
    cfg.legalMoves.forEach(function (m) {
        if (!legalMoveMap[m.from]) legalMoveMap[m.from] = [];
        legalMoveMap[m.from].push(m);
    });

    // ── Piece image helper ────────────────────────────────────────────────

    function pieceImgSrc(pieceChar) {
        var colour = pieceChar === pieceChar.toUpperCase() ? "w" : "b";
        return "/static/img/Chess_Pieces_Sprite.svg#" + colour + pieceChar.toUpperCase();
    }

    // ── Timer ─────────────────────────────────────────────────────────────

    function formatTime(seconds) {
        var m = Math.floor(seconds / 60);
        var s = seconds % 60;
        return m + ":" + (s < 10 ? "0" + s : s);
    }

    function updateTimerDisplay() {
        document.getElementById("whiteTime").textContent = formatTime(whiteTime);
        document.getElementById("blackTime").textContent = formatTime(blackTime);
    }

    function startTimer() {
        updateTimerDisplay();
        timerInterval = setInterval(function () {
            if (cfg.turn === "w") {
                whiteTime = Math.max(0, whiteTime - 1);
            } else {
                blackTime = Math.max(0, blackTime - 1);
            }
            updateTimerDisplay();

            if ((cfg.turn === "w" && whiteTime <= 0) || (cfg.turn === "b" && blackTime <= 0)) {
                clearInterval(timerInterval);
                if (cfg.isMyTurn) {
                    sendTimeout();
                }
            }
        }, 1000);
    }

    // ── Board setup ───────────────────────────────────────────────────────

    function initBoard() {
        var boardConfig = {
            position: cfg.boardFen,
            orientation: cfg.orientation,
            draggable: true,
            dropOffBoard: "snapback",
            pieceTheme: "/static/img/Chess_Pieces_Sprite.svg#{piece}",
            onDragStart: onDragStart,
            onDrop: onDrop,
            onMouseoverSquare: onMouseoverSquare,
            onMouseoutSquare: onMouseoutSquare,
        };
        board = Chessboard("myBoard", boardConfig);

        // Make board responsive
        $(window).on("resize", function () {
            board.resize();
        });
    }

    function onDragStart(source, piece) {
        if (!cfg.isMyTurn || dropMode || exchangeMode) return false;

        // Only allow dragging own pieces
        if (cfg.role === "white" && piece.charAt(0) === "b") return false;
        if (cfg.role === "black" && piece.charAt(0) === "w") return false;

        // Check if there are legal moves from this square
        var sq = source;
        if (!legalMoveMap[sq] || legalMoveMap[sq].length === 0) return false;

        return true;
    }

    function onDrop(source, target) {
        // Remove highlights
        clearHighlights();

        if (source === target) return "snapback";

        var moves = legalMoveMap[source] || [];
        var matching = moves.filter(function (m) { return m.to === target; });

        if (matching.length === 0) return "snapback";

        // Check for promotion
        if (matching.length > 1 || (matching.length === 1 && matching[0].promotion)) {
            showPromotionModal(source, target, matching);
            return; // Don't snap yet
        }

        submitMove(matching[0].from, matching[0].to, null);
    }



    function onMouseoverSquare(square) {
        if (!cfg.isMyTurn || dropMode || exchangeMode) return;

        var moves = legalMoveMap[square];
        if (!moves || moves.length === 0) return;

        // Highlight legal target squares
        var targets = {};
        moves.forEach(function (m) { targets[m.to] = true; });

        for (var sq in targets) {
            document.querySelector('[data-square="' + sq + '"]')
                ?.classList.add("highlight-legal");
        }
    }

    function onMouseoutSquare() {
        if (dropMode || exchangeMode) return;
        clearHighlights();
    }

    function clearHighlights() {
        document.querySelectorAll(".highlight-legal, .highlight-drop, .highlight-selected")
            .forEach(function (el) {
                el.classList.remove("highlight-legal", "highlight-drop", "highlight-selected");
            });
    }

    // ── Promotion modal ───────────────────────────────────────────────────

    function showPromotionModal(from, to, moves) {
        var modal = document.getElementById("promotion-modal");
        var container = document.getElementById("promotion-options");
        container.innerHTML = "";

        var pieces = cfg.role === "white" ? ["Q", "R", "B", "N"] : ["q", "r", "b", "n"];

        pieces.forEach(function (p) {
            var btn = document.createElement("button");
            btn.className = "promotion-btn";
            var img = document.createElement("img");
            img.src = pieceImgSrc(p);
            img.alt = p;
            btn.appendChild(img);
            btn.addEventListener("click", function () {
                modal.style.display = "none";
                submitMove(from, to, p);
            });
            container.appendChild(btn);
        });

        modal.style.display = "flex";
    }

    // ── Prison / Airfield display ─────────────────────────────────────────

    function renderHostagePanels() {
        var hs = cfg.hostageState;

        renderTray("player-prison", hs.playerPrison, false);
        renderTray("player-airfield", hs.playerAirfield, cfg.isMyTurn);
        renderTray("opponent-prison", hs.opponentPrison, false);
        renderTray("opponent-airfield", hs.opponentAirfield, false);

        // Reset drop/exchange buttons (disabled by default)
        var dropBtn = document.getElementById("btn-drop");
        var exchBtn = document.getElementById("btn-exchange");
        dropBtn.disabled = true;
        exchBtn.disabled = true;

        // Enable only when it's this player's turn and moves are available
        if (cfg.isMyTurn && cfg.dropMoves.length > 0) {
            dropBtn.disabled = false;
        }
        if (cfg.isMyTurn && cfg.exchangeOptions.length > 0) {
            exchBtn.disabled = false;
        }
    }

    function renderTray(elementId, pieces, clickable) {
        var tray = document.getElementById(elementId);
        tray.innerHTML = "";

        pieces.forEach(function (piece, idx) {
            var img = document.createElement("img");
            img.src = pieceImgSrc(piece);
            img.alt = piece;
            img.className = "tray-piece" + (clickable ? " clickable" : "");
            img.dataset.piece = piece;
            img.dataset.index = idx;

            if (clickable) {
                img.addEventListener("click", function () {
                    startDropMode(idx, piece);
                });
            }

            tray.appendChild(img);
        });
    }

    // ── Drop mode ─────────────────────────────────────────────────────────

    function startDropMode(airfieldIdx, piece) {
        if (dropMode && selectedAirfieldIdx === airfieldIdx) {
            cancelDropMode();
            return;
        }

        dropMode = true;
        selectedAirfieldIdx = airfieldIdx;

        // Highlight the selected piece
        clearTraySelection();
        var tray = document.getElementById("player-airfield");
        var imgs = tray.querySelectorAll(".tray-piece");
        if (imgs[airfieldIdx]) imgs[airfieldIdx].classList.add("selected");

        // Highlight valid drop squares
        clearHighlights();
        cfg.dropMoves.forEach(function (d) {
            if (d.airfieldIdx === airfieldIdx) {
                var sq = document.querySelector('[data-square="' + d.to + '"]');
                if (sq) sq.classList.add("highlight-drop");
            }
        });

        // Listen for square clicks
        document.getElementById("myBoard").addEventListener("click", onDropSquareClick);
        document.getElementById("status-text").textContent = "Click a square to drop " + piece.toUpperCase();
    }

    function onDropSquareClick(e) {
        if (!dropMode) return;

        var squareEl = e.target.closest("[data-square]");
        if (!squareEl) return;

        var sq = squareEl.getAttribute("data-square");

        // Check if this is a valid drop square
        var match = cfg.dropMoves.find(function (d) {
            return d.airfieldIdx === selectedAirfieldIdx && d.to === sq;
        });

        if (match) {
            cancelDropMode();
            submitDrop(match.airfieldIdx, match.to);
        }
    }

    function cancelDropMode() {
        dropMode = false;
        selectedAirfieldIdx = null;
        clearHighlights();
        clearTraySelection();
        document.getElementById("myBoard").removeEventListener("click", onDropSquareClick);
        if (cfg.isMyTurn) {
            document.getElementById("status-text").textContent = "Your turn";
        }
    }

    function clearTraySelection() {
        document.querySelectorAll(".tray-piece.selected").forEach(function (el) {
            el.classList.remove("selected");
        });
    }

    // ── Exchange mode ─────────────────────────────────────────────────────

    function startExchangeMode() {
        if (exchangeMode) {
            cancelExchangeMode();
            return;
        }

        exchangeMode = true;
        var modal = document.getElementById("exchange-modal");
        var container = document.getElementById("exchange-options");
        container.innerHTML = "";

        cfg.exchangeOptions.forEach(function (opt, idx) {
            var btn = document.createElement("button");
            btn.className = "exchange-btn";

            var rescueImg = document.createElement("img");
            rescueImg.src = pieceImgSrc(opt.rescue);
            rescueImg.alt = "Rescue " + opt.rescue;

            var payImg = document.createElement("img");
            payImg.src = pieceImgSrc(opt.payment);
            payImg.alt = "Pay " + opt.payment;

            var label = document.createElement("span");
            label.className = "exchange-label";
            label.textContent = "Rescue " + opt.rescue.toUpperCase() + " → Pay " + opt.payment.toUpperCase();

            btn.appendChild(rescueImg);
            btn.appendChild(payImg);
            btn.appendChild(label);

            btn.addEventListener("click", function () {
                selectedExchange = opt;
                document.getElementById("exchange-options").style.display = "none";
                document.getElementById("exchange-drop").style.display = "block";

                // Highlight valid squares for drop
                clearHighlights();
                opt.valid_drops.forEach(function (sqName) {
                    var sqEl = document.querySelector('[data-square="' + sqName + '"]');
                    if (sqEl) sqEl.classList.add("highlight-drop");
                });

                modal.style.display = "none";
                document.getElementById("myBoard").addEventListener("click", onExchangeDropClick, true);
            });

            container.appendChild(btn);
        });

        modal.style.display = "flex";
    }

    function onExchangeDropClick(e) {
        if (!exchangeMode || !selectedExchange) return;

        var squareEl = e.target.closest("[data-square]");
        if (!squareEl) return;

        e.stopPropagation();
        e.preventDefault();

        var sq = squareEl.getAttribute("data-square");
        if (selectedExchange.valid_drops.includes(sq)) {
            var rescue_idx = selectedExchange.rescue_idx;
            var payment_idx = selectedExchange.payment_idx;
            cancelExchangeMode();
            submitExchange(rescue_idx, payment_idx, sq);
        }
    }

    function cancelExchangeMode() {
        exchangeMode = false;
        selectedExchange = null;
        clearHighlights();
        document.getElementById("exchange-modal").style.display = "none";
        document.getElementById("exchange-options").style.display = "flex";
        document.getElementById("exchange-drop").style.display = "none";
        document.getElementById("myBoard").removeEventListener("click", onExchangeDropClick, true);
    }

    // ── Server communication ──────────────────────────────────────────────

    function submitMove(from, to, promotion) {
        clearInterval(timerInterval);
        sendJSON("/api/move", {
            game_no: cfg.gameNo,
            turn_no: cfg.turnNo,
            role: cfg.role,
            from: from,
            to: to,
            promotion: promotion,
        });
    }

    function submitDrop(airfieldIdx, to) {
        clearInterval(timerInterval);
        sendJSON("/api/drop", {
            game_no: cfg.gameNo,
            turn_no: cfg.turnNo,
            role: cfg.role,
            airfield_idx: airfieldIdx,
            to: to,
        });
    }

    function submitExchange(rescueIdx, paymentIdx, dropSquare) {
        clearInterval(timerInterval);
        sendJSON("/api/exchange", {
            game_no: cfg.gameNo,
            turn_no: cfg.turnNo,
            role: cfg.role,
            rescue_idx: rescueIdx,
            payment_idx: paymentIdx,
            drop_square: dropSquare,
        });
    }

    function sendTimeout() {
        sendJSON("/api/timeout", {
            game_no: cfg.gameNo,
            turn_no: cfg.turnNo,
        });
    }

    function submitResignation() {
        clearInterval(timerInterval);
        sendJSON("/api/resign", {
            game_no: cfg.gameNo,
            role: cfg.role,
        });
    }

    function sendJSON(url, data) {
        fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        })
            .then(function (r) { return r.json(); })
            .then(function (resp) {
                if (resp.game_over) {
                    window.location.href = "/game_over?game_no=" + cfg.gameNo;
                } else if (resp.ok) {
                    fetchAndRefresh(resp.new_turn_no);
                } else if (resp.error) {
                    alert("Error: " + resp.error);
                    fetchAndRefresh(cfg.turnNo);
                }
            })
            .catch(function (err) {
                console.error("Request failed:", err);
            });
    }

    // ── In-place refresh ──────────────────────────────────────────────────

    function fetchAndRefresh(turnNo) {
        var url = "/api/game_data?game_no=" + cfg.gameNo +
            "&turn_no=" + turnNo + "&role=" + cfg.role;
        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.game_over) {
                    window.location.href = "/game_over?game_no=" + cfg.gameNo;
                    return;
                }
                if (data.error) {
                    console.error("State fetch error:", data.error);
                    return;
                }
                refreshGameState(data, turnNo);
            })
            .catch(function (err) {
                console.error("Failed to fetch game state:", err);
            });
    }

    function refreshGameState(data, turnNo) {
        // Update config
        cfg.turnNo = turnNo;
        cfg.turn = data.turn;
        cfg.boardFen = data.boardFen;
        cfg.whiteTime = data.whiteTime;
        cfg.blackTime = data.blackTime;
        cfg.isMyTurn = data.isMyTurn;
        cfg.legalMoves = data.legalMoves;
        cfg.dropMoves = data.dropMoves;
        cfg.exchangeOptions = data.exchangeOptions;
        cfg.hostageState = data.hostageState;

        // Rebuild legal move lookup
        legalMoveMap = {};
        cfg.legalMoves.forEach(function (m) {
            if (!legalMoveMap[m.from]) legalMoveMap[m.from] = [];
            legalMoveMap[m.from].push(m);
        });

        // Update board position (animate the pieces)
        board.position(cfg.boardFen, true);

        // Update timers
        whiteTime = data.whiteTime;
        blackTime = data.blackTime;
        clearInterval(timerInterval);
        startTimer();

        // Reset modes
        dropMode = false;
        selectedAirfieldIdx = null;
        exchangeMode = false;
        selectedExchange = null;
        clearHighlights();
        clearTraySelection();

        // Update hostage panels
        renderHostagePanels();

        // Update status
        updateStatusText();

        // Restart polling for next state change
        startPolling();
    }

    function updateStatusText() {
        var el = document.getElementById("status-text");
        if (!el) return;
        if (cfg.isMyTurn) {
            el.textContent = "Your turn";
        } else {
            el.textContent = "Waiting for opponent…";
        }
    }

    // ── Polling (opponent's turn) ─────────────────────────────────────────

    var pollInterval = null;

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(function () {
            fetch("/api/poll?game_no=" + cfg.gameNo + "&turn_no=" + cfg.turnNo)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.game_over) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                        window.location.href = "/game_over?game_no=" + cfg.gameNo;
                    } else if (data.update_available) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                        fetchAndRefresh(data.new_turn_no);
                    }
                })
                .catch(function () { /* retry next interval */ });
        }, 1500);
    }

    // ── Initialisation ────────────────────────────────────────────────────

    $(document).ready(function () {
        initBoard();
        renderHostagePanels();
        startTimer();

        startPolling();

        // Button handlers
        document.getElementById("btn-drop").addEventListener("click", function () {
            if (dropMode) {
                cancelDropMode();
            } else {
                // Open airfield selection by highlighting first piece
                var af = cfg.hostageState.playerAirfield;
                if (af.length > 0) {
                    startDropMode(0, af[0]);
                }
            }
        });

        document.getElementById("btn-exchange").addEventListener("click", function () {
            startExchangeMode();
        });

        document.getElementById("cancel-exchange").addEventListener("click", function () {
            cancelExchangeMode();
        });

        document.getElementById("btn-resign").addEventListener("click", function () {
            if (confirm("Are you sure you want to resign and forfeit the game?")) {
                submitResignation();
            }
        });
    });
})();
