import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/api/app_models.dart';
import 'template_theme.dart';

class DramaVisualSeed {
  const DramaVisualSeed({
    required this.title,
    required this.tag,
    required this.heat,
    required this.palette,
    required this.mood,
  });

  final String title;
  final String tag;
  final String heat;
  final List<Color> palette;
  final String mood;
}

DramaVisualSeed dramaVisualSeedFor({
  required TemplateTokens tokens,
  required String title,
  required int index,
}) {
  final titleHash = title.codeUnits.fold<int>(index + 17, (sum, unit) {
    return (sum * 31 + unit) & 0x7fffffff;
  });
  final themes = switch (tokens.name) {
    'CoolShow Short' => const [
        'Hot',
        'Free',
        'Top',
        'New',
      ],
    'Vertical Pulse' => const [
        'Hot now',
        'Swipe pick',
        'Live cut',
        'New hook',
      ],
    'Channel Theater' => const [
        'VIP',
        '1080P',
        'Early access',
        'Trending',
      ],
    'Cliffhanger Premium' => const [
        'Exclusive',
        'Coins',
        'Trial',
        'Finale',
      ],
    _ => const [
        'Free',
        'New',
        'Hot',
        'Complete',
      ],
  };
  final moods = switch (tokens.name) {
    'CoolShow Short' => const [
        'Fast hook',
        'Contract love',
        'Coins unlock',
        'Trial member',
      ],
    'Vertical Pulse' => const [
        'Vertical feed',
        'Fast hook',
        'Comment heat',
        'Night cut',
      ],
    'Channel Theater' => const [
        'Theater lane',
        'VIP lane',
        'Ranking list',
        'Watch later',
      ],
    'Cliffhanger Premium' => const [
        'Billionaire',
        'Forbidden love',
        'Revenge',
        'Secret heir',
      ],
    _ => const [
        'Revenge',
        'Modern love',
        'Comeback',
        'Family secret',
      ],
  };
  final palette = _paletteFor(tokens, titleHash);
  return DramaVisualSeed(
    title: title,
    tag: themes[titleHash % themes.length],
    heat: '${((titleHash % 860) + 120) / 10}w heat',
    palette: palette,
    mood: moods[(titleHash ~/ 7) % moods.length],
  );
}

List<Color> _paletteFor(TemplateTokens tokens, int hash) {
  final base = <List<Color>>[
    [tokens.primary, tokens.secondary, tokens.posterTint],
    [tokens.secondary, tokens.primary, const Color(0xFF1E1B4B)],
    [const Color(0xFF111827), tokens.primary, tokens.secondary],
    [tokens.posterTint, tokens.secondary, const Color(0xFFFFF7ED)],
  ];
  final selected = base[hash % base.length];
  if (tokens.background.computeLuminance() < 0.25) {
    return [
      Color.lerp(selected[0], Colors.black, 0.16)!,
      selected[1],
      Color.lerp(selected[2], Colors.black, 0.42)!,
    ];
  }
  return [
    Color.lerp(selected[2], Colors.white, 0.22)!,
    selected[0],
    selected[1],
  ];
}

List<String> templateTabs(TemplateTokens tokens) {
  return switch (tokens.name) {
    'CoolShow Short' => const [
        'Romance',
        'Revenge',
        'Mystery',
        'Fresh ads',
      ],
    'Vertical Pulse' => const ['Recommend', 'Nearby', 'Following'],
    'Channel Theater' => const ['Recommend', 'Theater', 'Ranking', 'VIP'],
    'Cliffhanger Premium' => const [
        'For You',
        'New',
        'Billionaire',
        'Werewolf'
      ],
    _ => const ['Top', 'New', 'Revenge', 'Romance', 'Modern'],
  };
}

String templateHeroKicker(TemplateTokens tokens) {
  return switch (tokens.name) {
    'CoolShow Short' => 'Drama that starts fast',
    'Vertical Pulse' => 'Immersive vertical feed',
    'Channel Theater' => 'Theater channels · VIP',
    'Cliffhanger Premium' => 'Premium mini-series',
    _ => 'Free dramas · Theater',
  };
}

String templatePrimaryMetric(TemplateTokens tokens, CatalogDrama? drama) {
  final ready = drama?.readyEpisodeCount ?? 8;
  final total = drama?.episodeCount ?? 36;
  return switch (tokens.name) {
    'CoolShow Short' => '$ready/$total ready · coins/trial',
    'Vertical Pulse' => '$ready ready · swipe to unlock',
    'Channel Theater' => '$ready/$total ready · VIP ad-free',
    'Cliffhanger Premium' => '$ready episodes ready · coins/VIP',
    _ => '$ready/$total ready · trending',
  };
}

class DramaPosterCard extends StatelessWidget {
  const DramaPosterCard({
    required this.tokens,
    required this.title,
    required this.index,
    this.imageUrl,
    this.meta,
    this.compact = false,
    this.rank,
    this.onTap,
    super.key,
  });

  final TemplateTokens tokens;
  final String title;
  final int index;
  final String? imageUrl;
  final String? meta;
  final bool compact;
  final int? rank;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final seed = dramaVisualSeedFor(
      tokens: tokens,
      title: title,
      index: index,
    );
    final poster = ClipRRect(
      borderRadius: BorderRadius.circular(tokens.radius),
      child: Stack(
        fit: StackFit.expand,
        children: [
          _DemoBitmapLayer(
            imageUrl: imageUrl ?? demoPosterUrl(title, index),
            fallback: CustomPaint(
              painter: DramaPosterPainter(seed: seed, tokens: tokens),
            ),
          ),
          Positioned(
            left: 8,
            top: 8,
            child: _PosterBadge(label: seed.tag, tokens: tokens),
          ),
          if (rank != null)
            Positioned(
              right: 8,
              top: 8,
              child: _RankBadge(rank: rank!, tokens: tokens),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.84),
                  ],
                ),
              ),
              child: Padding(
                padding: EdgeInsets.fromLTRB(10, compact ? 40 : 64, 10, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      maxLines: compact ? 1 : 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: compact ? 12 : 14,
                        height: 1.12,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      meta ?? seed.heat,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.78),
                        fontSize: compact ? 10 : 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(tokens.radius),
      child: AspectRatio(aspectRatio: 0.68, child: poster),
    );
  }
}

class DramaSceneBackdrop extends StatelessWidget {
  const DramaSceneBackdrop({
    required this.tokens,
    required this.title,
    required this.index,
    this.imageUrl,
    this.child,
    this.overlay = true,
    super.key,
  });

  final TemplateTokens tokens;
  final String title;
  final int index;
  final String? imageUrl;
  final Widget? child;
  final bool overlay;

  @override
  Widget build(BuildContext context) {
    final seed = dramaVisualSeedFor(
      tokens: tokens,
      title: title,
      index: index,
    );
    return Stack(
      fit: StackFit.expand,
      children: [
        _DemoBitmapLayer(
          imageUrl: imageUrl ?? demoSceneUrl(title, index),
          fallback: CustomPaint(
              painter: DramaScenePainter(seed: seed, tokens: tokens)),
        ),
        if (overlay)
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.12),
                  Colors.transparent,
                  Colors.black.withValues(alpha: 0.9),
                ],
                stops: const [0, 0.42, 1],
              ),
            ),
          ),
        if (child != null) child!,
      ],
    );
  }
}

String demoPosterUrl(String title, int index) {
  return 'assets/visuals/poster_${_visualAssetIndex(index, 5)}.jpg';
}

String demoSceneUrl(String title, int index) {
  return 'assets/visuals/scene_${_visualAssetIndex(index, 3)}.jpg';
}

String _visualAssetIndex(int index, int count) {
  final value = (index.abs() % count) + 1;
  return value.toString().padLeft(2, '0');
}

class _DemoBitmapLayer extends StatelessWidget {
  const _DemoBitmapLayer({required this.imageUrl, required this.fallback});

  final String imageUrl;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    final uri = Uri.tryParse(imageUrl);
    if (uri == null || !uri.hasScheme) {
      return Stack(
        fit: StackFit.expand,
        children: [
          fallback,
          Image.asset(
            imageUrl,
            fit: BoxFit.cover,
            gaplessPlayback: true,
            errorBuilder: (_, __, ___) => const SizedBox.shrink(),
          ),
        ],
      );
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        fallback,
        Image.network(
          imageUrl,
          fit: BoxFit.cover,
          gaplessPlayback: true,
          errorBuilder: (_, __, ___) => const SizedBox.shrink(),
        ),
      ],
    );
  }
}

class DramaPosterPainter extends CustomPainter {
  const DramaPosterPainter({required this.seed, required this.tokens});

  final DramaVisualSeed seed;
  final TemplateTokens tokens;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final bg = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: seed.palette,
      ).createShader(rect);
    canvas.drawRect(rect, bg);

    _paintLight(canvas, size);
    _paintPortrait(canvas, size);
    _paintTexture(canvas, size);
  }

  void _paintLight(Canvas canvas, Size size) {
    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.white.withValues(alpha: 0.38),
          Colors.white.withValues(alpha: 0),
        ],
      ).createShader(
        Rect.fromCircle(
          center: Offset(size.width * 0.32, size.height * 0.22),
          radius: size.width * 0.72,
        ),
      );
    canvas.drawCircle(
      Offset(size.width * 0.32, size.height * 0.22),
      size.width * 0.72,
      glowPaint,
    );
  }

  void _paintPortrait(Canvas canvas, Size size) {
    final skin = Paint()..color = const Color(0xFFFFD7C2);
    final dark = Paint()..color = Colors.black.withValues(alpha: 0.54);
    final garment = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          Colors.white.withValues(alpha: 0.92),
          seed.palette[0].withValues(alpha: 0.82),
        ],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));

    final headCenter = Offset(size.width * 0.52, size.height * 0.34);
    canvas.drawOval(
      Rect.fromCenter(
        center: headCenter,
        width: size.width * 0.28,
        height: size.width * 0.34,
      ),
      skin,
    );
    canvas.drawArc(
      Rect.fromCenter(
        center: headCenter.translate(0, -size.width * 0.03),
        width: size.width * 0.36,
        height: size.width * 0.34,
      ),
      math.pi,
      math.pi,
      false,
      dark,
    );
    final bodyPath = Path()
      ..moveTo(size.width * 0.25, size.height * 0.92)
      ..cubicTo(
        size.width * 0.3,
        size.height * 0.58,
        size.width * 0.72,
        size.height * 0.58,
        size.width * 0.78,
        size.height * 0.92,
      )
      ..close();
    canvas.drawPath(bodyPath, garment);

    final second = Paint()..color = Colors.black.withValues(alpha: 0.24);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(size.width * 0.28, size.height * 0.45),
        width: size.width * 0.22,
        height: size.width * 0.28,
      ),
      second,
    );
  }

  void _paintTexture(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.18)
      ..strokeWidth = 1;
    for (var i = 0; i < 7; i += 1) {
      final y = size.height * (0.12 + i * 0.055);
      canvas.drawLine(
        Offset(size.width * (0.08 + i * 0.035), y),
        Offset(size.width * (0.42 + i * 0.045), y),
        linePaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant DramaPosterPainter oldDelegate) {
    return oldDelegate.seed != seed || oldDelegate.tokens != tokens;
  }
}

class DramaScenePainter extends CustomPainter {
  const DramaScenePainter({required this.seed, required this.tokens});

  final DramaVisualSeed seed;
  final TemplateTokens tokens;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final bg = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          seed.palette[0],
          seed.palette[1],
          Colors.black,
        ],
      ).createShader(rect);
    canvas.drawRect(rect, bg);

    final window = Paint()
      ..color = Colors.white.withValues(
        alpha: tokens.background.computeLuminance() < 0.25 ? 0.12 : 0.18,
      );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(
          size.width * 0.1,
          size.height * 0.12,
          size.width * 0.8,
          size.height * 0.38,
        ),
        const Radius.circular(18),
      ),
      window,
    );

    final facePaint = Paint()..color = const Color(0xFFFFD8C7);
    final hairPaint = Paint()..color = Colors.black.withValues(alpha: 0.58);
    final center = Offset(size.width * 0.5, size.height * 0.38);
    canvas.drawOval(
      Rect.fromCenter(
        center: center,
        width: size.width * 0.22,
        height: size.width * 0.28,
      ),
      facePaint,
    );
    canvas.drawArc(
      Rect.fromCenter(
        center: center.translate(0, -size.width * 0.03),
        width: size.width * 0.28,
        height: size.width * 0.28,
      ),
      math.pi,
      math.pi,
      false,
      hairPaint,
    );
    final coat = Paint()
      ..shader = LinearGradient(
        colors: [Colors.white, seed.palette[2]],
      ).createShader(rect);
    final path = Path()
      ..moveTo(size.width * 0.24, size.height * 0.68)
      ..cubicTo(
        size.width * 0.28,
        size.height * 0.5,
        size.width * 0.72,
        size.height * 0.5,
        size.width * 0.78,
        size.height * 0.68,
      )
      ..lineTo(size.width * 0.9, size.height)
      ..lineTo(size.width * 0.1, size.height)
      ..close();
    canvas.drawPath(path, coat);

    final caption = Paint()
      ..color = Colors.white.withValues(alpha: 0.78)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < 3; i += 1) {
      final y = size.height * (0.72 + i * 0.025);
      canvas.drawLine(
        Offset(size.width * 0.26, y),
        Offset(size.width * (0.74 - i * 0.08), y),
        caption,
      );
    }
  }

  @override
  bool shouldRepaint(covariant DramaScenePainter oldDelegate) {
    return oldDelegate.seed != seed || oldDelegate.tokens != tokens;
  }
}

class _PosterBadge extends StatelessWidget {
  const _PosterBadge({required this.label, required this.tokens});

  final String label;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: tokens.primary.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
        child: Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 10,
            fontWeight: FontWeight.w900,
          ),
        ),
      ),
    );
  }
}

class _RankBadge extends StatelessWidget {
  const _RankBadge({required this.rank, required this.tokens});

  final int rank;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 28,
      height: 28,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.62),
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white.withValues(alpha: 0.3)),
      ),
      child: Text(
        '$rank',
        style: TextStyle(
          color: tokens.secondary.computeLuminance() < 0.35
              ? Colors.white
              : tokens.secondary,
          fontWeight: FontWeight.w900,
          fontSize: 12,
        ),
      ),
    );
  }
}
